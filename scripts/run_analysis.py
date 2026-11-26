"""Run Kenneth's half of the project end to end.

Reads the raw parquet, builds sessions / player-days / avatars, runs Q1, Q2, Q3,
Q6 and the opportunity sizing, and writes:
  reports/headline_metrics.json   every number the README and memo quote
  reports/tables/*.csv            the tables behind each chart
  reports/tableau/*.csv           extracts for the Tableau dashboard
  reports/figures/*.png           charts
  data/interim/*.parquet          intermediate tables (gitignored)

Usage:
  python scripts/run_analysis.py --raw data/raw/wow-full.parquet
  python scripts/run_analysis.py --raw data/fixture/wow-fixture.parquet --out data/fixture_reports --quick
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments import design as ed  # noqa: E402
from experiments import population as ep  # noqa: E402
from growth import charts  # noqa: E402
from growth import data as gd  # noqa: E402
from growth import early as ge  # noqa: E402
from growth import launch as gl  # noqa: E402
from growth import metrics as gm  # noqa: E402
from growth import sizing as gs  # noqa: E402
from growth.io import write_table  # noqa: E402

# Figures reported by the dataset authors (Lee et al., MMSys 2011).
PAPER = {"avatars": 91065, "sessions": 667032, "expected_snapshots": 159408, "missing_snapshots": 21324, "days": 1107}

EVENTS_FILE = Path(__file__).resolve().parents[1] / "docs" / "event_calendar.csv"


T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def jsonable(x):
    if x is pd.NaT or x is None:
        return None
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else round(float(x), 6)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(x).strftime("%Y-%m-%d")
    if isinstance(x, pd.Period):
        return str(x)
    return x


def _sens_row(name, pre, trend, r):
    keys = ("lift", "ci_low", "ci_high")
    return {"launch": name, "pre_days": pre, "trend": trend, **{k: r[k] for k in keys}}


def _week_lift(weekly, name, week):
    return float(weekly.loc[(weekly["launch"] == name) & (weekly["week"] == week), "lift"].iloc[0])


def getv(summary, segment, col):
    """One value from a launch_cohorts summary, or None if the segment is empty."""
    hit = summary.loc[summary["segment"] == segment, col]
    return float(hit.iloc[0]) if len(hit) else None


def blackout_windows(events, launches):
    """Periods that placebo tests and experiment reference dates must avoid."""
    out = []
    for d in launches.values():
        out.append((d - pd.Timedelta(days=14), d + pd.Timedelta(days=63)))
    for _, e in events.loc[events["kind"] == "anomaly"].iterrows():
        out.append((e["start"] - pd.Timedelta(days=7), e["end"] + pd.Timedelta(days=28)))
    return out


def detect_waves(avatars, top=3):
    """Days with the most first-seen avatars, and what those avatars looked like."""
    a = avatars.copy()
    by_day = a.groupby("first_day").agg(
        new=("player_id", "size"),
        share_above_level_10=("first_level", lambda s: float((s > 10).mean())),
        share_never_above_level_1=("max_level", lambda s: float((s <= 1).mean())),
    )
    base = by_day["new"].rolling(29, center=True, min_periods=10).median()
    by_day["ratio_to_typical"] = by_day["new"] / base
    return by_day.sort_values("ratio_to_typical", ascending=False).head(top).reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw/wow-full.parquet")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--interim", default="data/interim")
    ap.add_argument("--quick", action="store_true", help="fewer bootstrap draws and simulations (CI)")
    args = ap.parse_args()
    out = Path(args.out)
    tables_dir, tableau_dir, fig_dir = out / "tables", out / "tableau", out / "figures"
    for p in (tables_dir, tableau_dir, fig_dir):
        p.mkdir(parents=True, exist_ok=True)
    n_boot = 200 if args.quick else 2000
    n_sims = 200 if args.quick else 2000
    H = {}

    # ------------------------------------------------------------ data layer
    log("loading raw snapshots")
    raw = gd.load_raw(args.raw)
    t = gd.build_all(raw)
    del raw
    for name in ["sweeps", "coverage", "sessions", "player_day", "avatars"]:
        write_table(t[name], Path(args.interim) / f"{name}.parquet")
    pday, cov, avatars, sessions = t["player_day"], t["coverage"], t["avatars"], t["sessions"]
    q = t["quality"]
    thin = t["thinning"]
    ratio = float(thin["ratio"].mean()) if len(thin) else float("nan")
    end = pday["date"].max()
    log(f"built tables: {q['player_days']:,} player-days, {q['sessions']:,} sessions")

    events = pd.read_csv(EVENTS_FILE, parse_dates=["start", "end"])
    launches = gl.detect_launch_dates(pday)
    waves = detect_waves(avatars)
    waves.to_csv(tables_dir / "dq_new_avatar_waves.csv", index=False)
    slow = cov.loc[cov["slow_sampling"], "date"]
    H["data_quality"] = {
        **q,
        "paper": PAPER,
        "avatars_vs_paper": q["raw_avatars"] - PAPER["avatars"],
        "sweeps_vs_paper_collected": q["sweeps"] - (PAPER["expected_snapshots"] - PAPER["missing_snapshots"]),
        "sessions_one_missed_sweep_allowed": q["sessions"],
        "low_coverage_days": int((cov["coverage"] < gm.LOW_COVERAGE).sum()),
        "slow_sampling_start": slow.min() if len(slow) else None,
        "slow_sampling_days": int(len(slow)),
        "thinning_dau_ratio": ratio,
        "thinning_days": int(len(thin)),
        "launch_dates": launches,
        "waves": waves.to_dict("records"),
    }

    # ------------------------------------------------------------ Q1
    log("Q1 growth accounting and retention")
    daily = gm.daily_active(pday, cov, ratio if np.isfinite(ratio) else None)
    daily.to_csv(tableau_dir / "daily_active.csv", index=False)
    # First day of the last month with complete data (a partial final month is left out).
    last_full_month = (end + pd.Timedelta(days=1)).to_period("M").to_timestamp()
    ga = gm.monthly_growth_accounting(pday, end=last_full_month)
    ga.drop(columns=["month"]).to_csv(tableau_dir / "growth_accounting_monthly.csv", index=False)
    decomp = gm.change_decomposition(ga)
    # Same split without the two anomaly months (transfer wave, level-1 wave).
    anomaly_months = [pd.Period(e, "M") for e in events.loc[events["kind"] == "anomaly", "start"]]
    ga_clean = ga.loc[~ga["month"].isin(anomaly_months)]
    decomp_clean = gm.change_decomposition(ga_clean) if len(ga_clean) > 3 else {}
    cohort = gm.new_avatars(avatars, end - pd.Timedelta(days=120))
    flags = gm.retention_flags(pday, cohort)
    flags["cohort_month"] = flags["first_day"].dt.to_period("M").dt.to_timestamp()
    ret_month = flags.groupby("cohort_month")[["d1", "d7", "d30", "d90"]].mean().reset_index()
    ret_month["new_avatars"] = flags.groupby("cohort_month").size().to_numpy()
    ret_month.to_csv(tables_dir / "q1_new_avatar_retention_by_month.csv", index=False)
    all_new = gm.new_avatars(avatars, end)
    cr = gm.monthly_cohort_retention(pday, all_new, last_month=last_full_month - pd.Timedelta(days=1))
    cr.drop(columns=["cohort"]).to_csv(tableau_dir / "cohort_retention.csv", index=False)
    ok = daily.loc[~daily["low_coverage"] & (daily["date"] >= gm.BURN_IN_END)]
    gross = ga[["new", "resurrected"]].sum()
    H["q1"] = {
        "avg_dau": ok["dau_adj"].mean(),
        "peak_dau": ok["dau_adj"].max(),
        "peak_dau_date": ok.loc[ok["dau_adj"].idxmax(), "date"],
        "avg_mau": ok["mau"].mean(),
        "avg_stickiness": ok["stickiness"].mean(),
        "avg_minutes_per_dau": ok["minutes_per_dau"].mean(),
        "months": len(ga),
        "first_month": ga["month"].iloc[0],
        "last_month": ga["month"].iloc[-1],
        "share_gross_adds_new": gross["new"] / gross.sum(),
        "share_gross_adds_resurrected": gross["resurrected"] / gross.sum(),
        "avg_resurrected_per_month": ga["resurrected"].mean(),
        "avg_new_per_month": ga["new"].mean(),
        "avg_churned_per_month": ga["churned"].mean(),
        "months_quick_ratio_above_1": int((ga["quick_ratio"] > 1).sum()),
        "median_quick_ratio": ga["quick_ratio"].median(),
        "mau_change_variance_share": decomp,
        "mau_change_variance_share_without_anomaly_months": decomp_clean,
        "new_avatar_cohort": len(cohort),
        "retention": flags[["d1", "d7", "d30", "d90"]].mean().to_dict(),
        "top_quick_ratio_months": ga.nlargest(3, "quick_ratio")[
            ["month", "quick_ratio", "new", "resurrected", "churned"]
        ].to_dict("records"),
    }

    # ------------------------------------------------------------ Q2
    log("Q2 launch impact")
    blackout = blackout_windows(events, launches)
    reused = avatars.loc[avatars["reused_id"], "player_id"]
    # Anomaly days stay out of the counterfactual fits (the wave itself plus a few days).
    anomaly_rows = events.loc[events["kind"] == "anomaly"]
    anomalies = [(e["start"], e["end"] + pd.Timedelta(days=3)) for _, e in anomaly_rows.iterrows()]
    post_days = {}
    for name, d in launches.items():
        post_days[name] = int(min(56, (end - d).days + 1))
    results, sens_rows, weekly_rows, series_rows = {}, [], [], []
    for name, d in launches.items():
        r = gl.counterfactual_lift(daily, d, pre_days=84, post_days=post_days[name], n_boot=n_boot, exclude=anomalies)
        results[name] = r
        for pre, trend in [(56, True), (112, True), (28, False)]:
            s = gl.counterfactual_lift(
                daily, d, pre_days=pre, post_days=post_days[name], trend=trend, n_boot=n_boot // 4, exclude=anomalies
            )
            sens_rows.append(_sens_row(name, pre, trend, s))
        sens_rows.append(_sens_row(name, 84, True, r))
        w = gl.weekly_lift(r)
        w.insert(0, "launch", name)
        weekly_rows.append(w)
        sr = r["series"].copy()
        sr.insert(0, "launch", name)
        series_rows.append(sr)
    sens = pd.DataFrame(sens_rows)
    sens.to_csv(tables_dir / "q2_launch_sensitivity.csv", index=False)
    weekly = pd.concat(weekly_rows)
    weekly.to_csv(tables_dir / "q2_weekly_lift.csv", index=False)
    pd.concat(series_rows).to_csv(tableau_dir / "launch_impact.csv", index=False)
    cands = pd.date_range(gm.BURN_IN_END, end, freq="14D")
    plac = gl.placebo_lifts(daily, cands, blackout, pre_days=84, post_days=56)
    plac.to_csv(tables_dir / "q2_placebos.csv", index=False)
    cohort_rows = []
    H["q2"] = {
        "placebo_n": len(plac),
        "placebo_sd": plac["lift"].std() if len(plac) else None,
        "placebo_max_abs": plac["lift"].abs().max() if len(plac) else None,
    }
    for name, d in launches.items():
        r = results[name]
        years = [
            y
            for y in (d.year - 1, d.year + 1)
            if pd.Timestamp(year=y, month=1, day=1) >= daily["date"].min()
            and d + pd.DateOffset(years=y - d.year) + pd.Timedelta(days=post_days[name]) <= end
        ]
        yoy = gl.yoy_lift(daily, d, years, post_days=post_days[name]) if years else {"lift": None}
        seg, summ = gl.launch_cohorts(pday, d, exclude_ids=reused)
        seg0, summ0 = gl.launch_cohorts(pday, d - pd.Timedelta(days=91), exclude_ids=reused)
        days_by_seg = gl.segment_days(pday, d, seg, days=post_days[name])
        for label, sm in [("launch", summ), ("91 days earlier", summ0)]:
            sm = sm.copy()
            sm.insert(0, "date_type", label)
            sm.insert(0, "launch", name)
            cohort_rows.append(sm)
        empirical_p = float((plac["lift"].abs() >= abs(r["lift"])).mean()) if len(plac) else None
        with_anomalies = gl.counterfactual_lift(daily, d, pre_days=84, post_days=post_days[name], n_boot=n_boot // 4)
        H["q2"][name] = {
            "launch_date": d,
            "lift_with_anomaly_days_in_fit": with_anomalies["lift"],
            "ci_with_anomaly_days_in_fit": [with_anomalies["ci_low"], with_anomalies["ci_high"]],
            "post_days": post_days[name],
            "lift": r["lift"],
            "ci": [r["ci_low"], r["ci_high"]],
            "actual_dau": r["actual_dau"],
            "counterfactual_dau": r["counterfactual_dau"],
            "extra_player_days": r["extra_player_days"],
            "week1_lift": _week_lift(weekly, name, 1),
            "last_full_week_lift": _week_lift(weekly, name, min(8, post_days[name] // 7)),
            "sensitivity_min": float(sens.loc[sens["launch"] == name, "lift"].min()),
            "sensitivity_max": float(sens.loc[sens["launch"] == name, "lift"].max()),
            "yoy": yoy,
            "placebo_share_as_large": empirical_p,
            "entrants": int(summ["players"].sum()),
            "share_new": getv(summ, "new", "share_of_entrants"),
            "share_reactivated": getv(summ, "reactivated", "share_of_entrants"),
            "share_already_active": getv(summ, "already active", "share_of_entrants"),
            "still_active_reactivated": getv(summ, "reactivated", "still_active"),
            "still_active_already_active": getv(summ, "already active", "still_active"),
            "still_active_new": getv(summ, "new", "still_active"),
            "baseline_still_active_reactivated": getv(summ0, "reactivated", "still_active"),
            "baseline_still_active_new": getv(summ0, "new", "still_active"),
            "player_days_by_segment": dict(zip(days_by_seg["segment"], days_by_seg["player_days"], strict=True)),
        }
    pd.concat(cohort_rows).to_csv(tables_dir / "q2_launch_cohorts.csv", index=False)

    # ------------------------------------------------------------ Q3
    log("Q3 early behaviors and guild effect")
    feats = ge.first_week_features(pday, sessions, cohort)
    best, scans = ge.aha_moments(feats)
    best.to_csv(tables_dir / "q3_aha_best.csv", index=False)
    scans.to_csv(tables_dir / "q3_aha_scan.csv", index=False)
    sample = ge.guild_study_sample(feats)
    res = ge.guild_effect(sample, n_boot=n_boot // 10 if args.quick else 500)
    res["balance"].to_csv(tables_dir / "q3_guild_balance.csv", index=False)
    by_days = feats.groupby("active_days_w1")["retained_d90"].agg(["mean", "size"]).reset_index()
    by_days.columns = ["active_days_w1", "retention_d90", "avatars"]
    by_days.to_csv(tables_dir / "q3_retention_by_week1_days.csv", index=False)
    top = best.iloc[0]
    H["q3"] = {
        "cohort": len(feats),
        "cohort_first_day_range": [feats["first_day"].min(), feats["first_day"].max()],
        "d90_retention": feats["retained_d90"].mean(),
        "aha_feature": top["feature"],
        "aha_threshold": top["threshold"],
        "aha_share": top["share_at_or_above"],
        "aha_retention_at_or_above": top["retention_at_or_above"],
        "aha_retention_below": top["retention_below"],
        "aha_lift": top["lift"],
        "aha_youden_j": top["youden_j"],
        "aha_table": best.to_dict("records"),
        "guild_in_week1_share": float(feats["guild_w1"].fillna(False).astype(bool).mean()),
        "guild": {k: v for k, v in res.items() if k != "balance"},
    }

    # ------------------------------------------------------------ Q6
    log("Q6 experiment design")
    ref_dates = ep.reference_dates(gm.BURN_IN_END + pd.Timedelta(days=28), end - pd.Timedelta(days=28), 28, blackout)
    pop, daily_mat = ep.pooled_population(pday, ref_dates)
    y = pop["y_days"].to_numpy(float)
    X = pop[["pre_days", "pre_hours"]].to_numpy(float)
    adj1, vr1 = ed.cuped(y, pop["pre_days"].to_numpy(float))
    adj2, vr2 = ed.cuped(y, X)
    sd_raw, sd_cup = float(y.std()), float(adj2.std())
    per_snapshot = pop.groupby("ref_date").size()
    power_rows = []
    for rel in [0.05, 0.10, 0.20]:
        mde = rel * y.mean()
        n_raw = ed.sample_size_mean(sd_raw, mde)
        n_cup = ed.sample_size_mean(sd_cup, mde)
        power_rows.append(
            {
                "relative_lift": rel,
                "absolute_lift_days": mde,
                "n_per_arm_raw": n_raw,
                "n_per_arm_cuped": n_cup,
                "four_week_cohorts_needed_cuped": 2 * n_cup / per_snapshot.mean(),
            }
        )
    power = pd.DataFrame(power_rows)
    power.to_csv(tables_dir / "q6_power.csv", index=False)
    n_arm = int(min(5000, len(pop) // 4))
    eff = ed.mde_mean(sd_cup, n_arm)
    aa = ed.aa_simulation(y, X, n_arm, n_sims=2 * n_sims)
    inj = ed.injection_simulation(y, X, eff, n_arm, cap=ep.TEST_DAYS, n_sims=n_sims // 2)
    peek = ed.peeking_simulation(daily_mat, int(min(1000, len(pop) // 4)), n_sims=n_sims)
    retained_rate = float(pop["retained"].mean())
    minutes_per_day = (pop["pre_hours"] * 60 / pop["pre_days"]).to_numpy()
    H["q6"] = {
        "reference_dates": len(ref_dates),
        "population_rows": len(pop),
        "at_risk_per_snapshot": per_snapshot.mean(),
        "y_mean": y.mean(),
        "y_sd": sd_raw,
        "y_share_zero": float((y == 0).mean()),
        "corr_pre_days": float(np.corrcoef(y, X[:, 0])[0, 1]),
        "cuped_variance_reduction_one_covariate": vr1,
        "cuped_variance_reduction": vr2,
        "sample_size_cut": 1 - power.loc[0, "n_per_arm_cuped"] / power.loc[0, "n_per_arm_raw"],
        "power_table": power.to_dict("records"),
        "sim_n_per_arm": n_arm,
        "aa_sims": 2 * n_sims,
        "injection_sims": n_sims // 2,
        "peeking_sims": n_sims,
        "sim_effect_days": eff,
        "sim_effect_relative": eff / y.mean(),
        "aa": aa,
        "injection": inj,
        "peeking": peek,
        "srm_example_p_50_50": ed.srm_test(5000, 5000),
        "srm_example_p_50_5": ed.srm_test(5050, 4950),
        "srm_example_p_52": ed.srm_test(5200, 4800),
        "secondary_retained_rate": retained_rate,
        "secondary_n_per_arm_2pts": ed.sample_size_prop(retained_rate, 0.02),
        "guardrail_minutes_per_active_day_median": float(np.median(minutes_per_day)),
    }

    # ------------------------------------------------------------ sizing
    log("opportunity sizing")
    sz = gs.size_d30_lift(pday, avatars, daily, points=1.0, forecast_path=str(out / "dau_forecast.csv"))
    pd.DataFrame({"day": np.arange(len(sz["extra_by_day"])), "extra_dau": sz["extra_by_day"]}).to_csv(
        tables_dir / "sizing_extra_dau.csv", index=False
    )
    H["sizing"] = {k: v for k, v in sz.items() if k not in ("curve", "extra_by_day")}

    # ------------------------------------------------------------ charts
    log("charts")
    ev = [(launches["tbc"], "Burning Crusade"), (launches["wotlk"], "Wrath of the Lich King")]
    transfer = events.loc[events["event"].str.contains("transfers"), "start"]
    if len(transfer):
        ev.insert(0, (transfer.iloc[0], "Transfer wave"))
    charts.dau_history(daily, ev, fig_dir / "dau_history.png")
    charts.growth_accounting(ga, fig_dir / "growth_accounting.png")
    charts.launch_panels(
        {"Burning Crusade": results["tbc"], "Wrath of the Lich King": results["wotlk"]}, fig_dir / "launch_impact.png"
    )
    charts.cohort_heatmap(cr, fig_dir / "cohort_retention.png")
    aha_days = int(top["threshold"]) if top["feature"] == "active_days_w1" else 2
    charts.aha_bars(feats, fig_dir / "aha_week1_days.png", aha_days)
    charts.guild_estimates(res, fig_dir / "guild_effect.png")
    charts.power_curves(sd_raw, sd_cup, y.mean(), fig_dir / "power_curves.png")

    (out / "headline_metrics.json").write_text(json.dumps(jsonable(H), indent=2) + "\n")
    log(f"wrote {out / 'headline_metrics.json'}")


if __name__ == "__main__":
    main()
