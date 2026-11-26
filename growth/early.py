"""Q3: which first-week behaviors predict day-90 retention, and does joining a
guild early cause higher retention?

Timeline for the guild study (days since an avatar was first seen):
  days 0-6    baseline behavior (covariates); avatars already in a guild are excluded
  days 7-13   treatment window: joins a guild for the first time, or does not
  days 90-119 outcome: active on at least one day
Covariates come strictly before treatment, so they cannot be caused by it.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import NearestNeighbors

WEEK1 = (0, 7)
TREAT_WINDOW = (7, 14)
OUTCOME_WINDOW = (90, 120)

NUMERIC_FEATURES = ["active_days_w1", "hours_w1", "sessions_w1", "levels_gained_w1", "max_level_w1", "first_level"]


def _age(dates, first_day):
    return ((dates - first_day) / pd.Timedelta(days=1)).astype(int)


def first_week_features(pday, sessions, cohort):
    """Behavior in days 0-6 plus guild timing and the day-90 outcome, one row per avatar."""
    c = cohort[["player_id", "first_day", "first_level", "race", "char_class", "first_guild_day"]].copy()
    d = pday.loc[pday["player_id"].isin(c["player_id"])].merge(c[["player_id", "first_day"]], on="player_id")
    d["age"] = _age(d["date"], d["first_day"])
    w1 = d.loc[(d["age"] >= WEEK1[0]) & (d["age"] < WEEK1[1])]
    g = w1.groupby("player_id")
    feats = pd.DataFrame(
        {
            "active_days_w1": g.size(),
            "hours_w1": g["minutes"].sum() / 60,
            "max_level_w1": g["max_level"].max(),
            "guild_w1": g["in_guild"].any(),
        }
    )
    s = sessions.loc[sessions["player_id"].isin(c["player_id"]), ["player_id", "start"]]
    s = s.merge(c[["player_id", "first_day"]], on="player_id")
    s_age = _age(s["start"].dt.normalize(), s["first_day"])
    sess = s.loc[(s_age >= WEEK1[0]) & (s_age < WEEK1[1])].groupby("player_id").size()
    w2 = d.loc[(d["age"] >= TREAT_WINDOW[0]) & (d["age"] < TREAT_WINDOW[1])]
    active_w2 = set(w2["player_id"].unique())
    out_ids = set(d.loc[(d["age"] >= OUTCOME_WINDOW[0]) & (d["age"] < OUTCOME_WINDOW[1]), "player_id"].unique())
    f = c.set_index("player_id").join(feats)
    f["sessions_w1"] = sess.reindex(f.index).fillna(0).astype(int)
    f["levels_gained_w1"] = f["max_level_w1"] - f["first_level"]
    f["guild_age"] = (f["first_guild_day"] - f["first_day"]) / pd.Timedelta(days=1)
    f["active_w2"] = f.index.isin(active_w2)
    f["retained_d90"] = f.index.isin(out_ids)
    f["cohort_quarter"] = f["first_day"].dt.to_period("Q").astype(str)
    return f.reset_index()


def threshold_search(df, feature, outcome="retained_d90", min_share=0.05):
    """Scan thresholds "feature >= k" and score each by Youden's J.

    J = (share of retained avatars at or above k) - (share of churned avatars at
    or above k). The best k separates retained from churned avatars most cleanly.
    Thresholds that leave fewer than `min_share` of avatars on either side are skipped.
    """
    x = df[feature].to_numpy()
    y = df[outcome].to_numpy().astype(bool)
    # Candidate thresholds are observed values, so "k" is always a real count or level.
    vals = np.unique(np.quantile(x, np.linspace(0.02, 0.98, 49), method="higher"))
    rows = []
    for k in vals:
        above = x >= k
        share = above.mean()
        if share < min_share or share > 1 - min_share:
            continue
        tpr = above[y].mean()
        fpr = above[~y].mean()
        rows.append(
            {
                "feature": feature,
                "threshold": float(k),
                "share_at_or_above": float(share),
                "retention_at_or_above": float(y[above].mean()),
                "retention_below": float(y[~above].mean()),
                "youden_j": float(tpr - fpr),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["lift"] = out["retention_at_or_above"] / out["retention_below"]
    return out


def aha_moments(df, features=None, outcome="retained_d90"):
    """Best threshold per feature, sorted by Youden's J."""
    features = features or ["active_days_w1", "hours_w1", "sessions_w1", "levels_gained_w1", "max_level_w1"]
    best = []
    scans = []
    for f in features:
        s = threshold_search(df, f, outcome)
        if s.empty:
            continue
        scans.append(s)
        best.append(s.loc[s["youden_j"].idxmax()])
    return pd.DataFrame(best).sort_values("youden_j", ascending=False).reset_index(drop=True), pd.concat(scans)


# ---------------------------------------------------------------- guild study
def guild_study_sample(features):
    """Eligible avatars and the treatment flag.

    Eligible: no guild in days 0-6 and active at least once in days 7-13.
    Treated: first guild in days 7-13. Control: no guild by day 13.
    """
    f = features
    eligible = (~f["guild_w1"].fillna(False).astype(bool)) & f["active_w2"]
    joined_late = f["guild_age"].between(TREAT_WINDOW[0], TREAT_WINDOW[1] - 1)
    no_guild_yet = f["guild_age"].isna() | (f["guild_age"] >= TREAT_WINDOW[1])
    s = f.loc[eligible & (joined_late | no_guild_yet)].copy()
    s["treated"] = joined_late.loc[s.index].astype(int)
    for col in NUMERIC_FEATURES:
        s[col] = s[col].fillna(0)
    return s.reset_index(drop=True)


def design_matrix(s, expanded=False):
    """Covariates for the propensity model.

    The plain version (used for the balance table) has the numeric features and
    dummies. The expanded version (used to fit the model) adds log and squared
    terms, since hours, sessions and levels are heavily skewed.
    """
    num = s[NUMERIC_FEATURES].astype(float)
    if expanded:
        for col in ["hours_w1", "sessions_w1", "levels_gained_w1", "max_level_w1"]:
            num[f"log_{col}"] = np.log1p(num[col].clip(lower=0))
        for col in ["active_days_w1", "levels_gained_w1"]:
            num[f"sq_{col}"] = num[col] ** 2
    num = (num - num.mean()) / num.std(ddof=0).replace(0, 1)
    cats = pd.get_dummies(s[["race", "char_class", "cohort_quarter"]].astype(str), drop_first=True, dtype=float)
    return pd.concat([num, cats], axis=1)


def propensity(X, t):
    model = LogisticRegression(C=1e6, max_iter=5000)
    model.fit(X, t)
    return model.predict_proba(X)[:, 1]


def smd(x, t, w=None):
    """Standardized mean difference (treated minus control) with optional control weights."""
    x = np.asarray(x, dtype=float)
    t = np.asarray(t).astype(bool)
    w = np.ones(len(x)) if w is None else np.asarray(w, dtype=float)
    m1 = x[t].mean()
    m0 = np.average(x[~t], weights=w[~t])
    # Pooled SD from the unweighted groups, so before and after share one scale.
    pooled = np.sqrt((x[t].var() + x[~t].var()) / 2)
    return (m1 - m0) / pooled if pooled > 0 else 0.0


def att_ipw(y, t, ps):
    """Average effect on the treated with odds weights for controls."""
    t = np.asarray(t).astype(bool)
    y = np.asarray(y, dtype=float)
    w = ps / (1 - ps)
    p1 = y[t].mean()
    p0 = np.average(y[~t], weights=w[~t])
    return p1, p0, w


def att_matching(y, t, ps, caliper_sd=0.2):
    """1:1 nearest-neighbor matching on the logit of the propensity score, with
    replacement, inside a caliper of `caliper_sd` standard deviations."""
    t = np.asarray(t).astype(bool)
    y = np.asarray(y, dtype=float)
    logit = np.log(ps / (1 - ps))
    cal = caliper_sd * logit.std()
    nn = NearestNeighbors(n_neighbors=1).fit(logit[~t].reshape(-1, 1))
    dist, idx = nn.kneighbors(logit[t].reshape(-1, 1))
    ok = dist[:, 0] <= cal
    y_c = y[~t][idx[ok, 0]]
    p1 = y[t][ok].mean()
    p0 = y_c.mean()
    return p1, p0, float(ok.mean())


def e_value(rr):
    """VanderWeele & Ding E-value for a risk ratio (protective ratios are inverted)."""
    rr = 1 / rr if rr < 1 else rr
    return rr + np.sqrt(rr * (rr - 1))


def guild_effect(sample, n_boot=200, seed=0, trim=(0.01, 0.99)):
    """Naive, IPW and matched estimates of the guild effect on day-90 retention."""
    X = design_matrix(sample)
    Xe = design_matrix(sample, expanded=True)
    t = sample["treated"].to_numpy()
    y = sample["retained_d90"].to_numpy().astype(float)
    ps = propensity(Xe, t)
    keep = (ps > trim[0]) & (ps < trim[1])
    X, Xe, t, y, ps = X.loc[keep], Xe.loc[keep], t[keep], y[keep], ps[keep]
    naive1, naive0 = y[t == 1].mean(), y[t == 0].mean()
    p1, p0, w = att_ipw(y, t, ps)
    m1, m0, matched_share = att_matching(y, t, ps)
    balance = pd.DataFrame(
        {
            "covariate": X.columns,
            "smd_before": [smd(X[c], t) for c in X.columns],
            "smd_after_ipw": [smd(X[c], t, w) for c in X.columns],
        }
    )
    rng = np.random.default_rng(seed)
    boots = []
    n = len(y)
    Xv = Xe.to_numpy()
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        if t[i].min() == t[i].max():
            continue
        ps_b = np.clip(
            LogisticRegression(C=1e6, max_iter=5000).fit(Xv[i], t[i]).predict_proba(Xv[i])[:, 1], 1e-6, 1 - 1e-6
        )
        b1, b0, _ = att_ipw(y[i], t[i], ps_b)
        boots.append((b1 - b0, b1 / b0))
    boots = np.array(boots).reshape(-1, 2)
    if len(boots):
        rd_lo, rd_hi = np.percentile(boots[:, 0], [2.5, 97.5])
        rr_lo, rr_hi = np.percentile(boots[:, 1], [2.5, 97.5])
    else:
        rd_lo = rd_hi = rr_lo = rr_hi = np.nan
    # Overlap check: how many controls the weights effectively use, and whether
    # any single control carries a large share of the weight.
    wc = w[t == 0]
    ess = wc.sum() ** 2 / (wc**2).sum()
    rr = p1 / p0
    return {
        "n": int(n),
        "n_treated": int(t.sum()),
        "trimmed": int((~keep).sum()),
        "naive_treated": float(naive1),
        "naive_control": float(naive0),
        "naive_rd": float(naive1 - naive0),
        "selection_share_of_naive_gap": float(1 - (p1 - p0) / (naive1 - naive0)) if naive1 != naive0 else None,
        "ipw_treated": float(p1),
        "ipw_control": float(p0),
        "ipw_rd": float(p1 - p0),
        "ipw_rd_ci": [float(rd_lo), float(rd_hi)],
        "ipw_rr": float(rr),
        "ipw_rr_ci": [float(rr_lo), float(rr_hi)],
        "match_treated": float(m1),
        "match_control": float(m0),
        "match_rd": float(m1 - m0),
        "matched_share": matched_share,
        "e_value": float(e_value(rr)),
        "e_value_ci": float(e_value(rr_lo)) if rr_lo > 1 else 1.0,
        "control_effective_n": float(ess),
        "controls": int((t == 0).sum()),
        "max_control_weight_share": float(wc.max() / wc.sum()),
        "max_abs_smd_before": float(balance["smd_before"].abs().max()),
        "max_abs_smd_after": float(balance["smd_after_ipw"].abs().max()),
        "balance": balance,
    }
