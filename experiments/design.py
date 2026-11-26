"""Power, CUPED, SRM, and the simulations that check them on real data."""

import numpy as np
from scipy import stats


# ---------------------------------------------------------------- power
def sample_size_mean(sd, mde, alpha=0.05, power=0.8):
    """Players per arm for a two-sided test of a difference in means."""
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return int(np.ceil(2 * (z * sd / mde) ** 2))


def mde_mean(sd, n_per_arm, alpha=0.05, power=0.8):
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return float(z * sd * np.sqrt(2 / n_per_arm))


def sample_size_prop(p, mde, alpha=0.05, power=0.8):
    """Players per arm to detect an absolute change `mde` from baseline rate `p`."""
    p2 = p + mde
    pbar = (p + p2) / 2
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    num = (za * np.sqrt(2 * pbar * (1 - pbar)) + zb * np.sqrt(p * (1 - p) + p2 * (1 - p2))) ** 2
    return int(np.ceil(num / mde**2))


# ---------------------------------------------------------------- CUPED
def cuped(y, x):
    """CUPED adjustment with one or more pre-period covariates.

    theta comes from regressing y on x over the whole sample (both arms), which
    keeps the adjusted metric unbiased under randomization.
    Returns (adjusted y, variance reduction).
    """
    y = np.asarray(y, dtype=float)
    X = np.asarray(x, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    Xc = X - X.mean(axis=0)
    theta, *_ = np.linalg.lstsq(Xc, y - y.mean(), rcond=None)
    adj = y - Xc @ theta
    return adj, float(1 - adj.var() / y.var())


def welch_p(a, b):
    return float(stats.ttest_ind(a, b, equal_var=False).pvalue)


def cuped_test(y, x, t):
    """Effect estimate and p-value on CUPED-adjusted y."""
    adj, _ = cuped(y, x)
    t = np.asarray(t).astype(bool)
    return float(adj[t].mean() - adj[~t].mean()), welch_p(adj[t], adj[~t])


# ---------------------------------------------------------------- SRM
def srm_test(n_treat, n_control, expected_share=0.5):
    """Chi-square test that the split matches the planned share."""
    total = n_treat + n_control
    exp = np.array([expected_share, 1 - expected_share]) * total
    chi2 = ((np.array([n_treat, n_control]) - exp) ** 2 / exp).sum()
    return float(stats.chi2.sf(chi2, df=1))


# ---------------------------------------------------------------- simulations
def _draw(n_total, n_per_arm, rng):
    idx = rng.choice(n_total, size=2 * n_per_arm, replace=False)
    t = np.zeros(2 * n_per_arm, dtype=bool)
    t[:n_per_arm] = True
    return idx, t


def aa_simulation(y, x, n_per_arm, n_sims=2000, alpha=0.05, seed=0):
    """Random splits of real players with no treatment: how often is p < alpha?"""
    rng = np.random.default_rng(seed)
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    raw = cup = 0
    for _ in range(n_sims):
        idx, t = _draw(len(y), n_per_arm, rng)
        raw += welch_p(y[idx][t], y[idx][~t]) < alpha
        cup += cuped_test(y[idx], x[idx], t)[1] < alpha
    return {"false_positive_raw": raw / n_sims, "false_positive_cuped": cup / n_sims}


def inject_effect(y_treated, effect, cap, rng):
    """Add one active day to each treated player with probability `effect`
    (so the average effect is about `effect` days), without exceeding `cap`."""
    bump = rng.random(len(y_treated)) < effect
    return np.minimum(y_treated + bump, cap)


def injection_simulation(y, x, effect, n_per_arm, cap, n_sims=1000, alpha=0.05, seed=0):
    """Plant a known effect in real data and measure power and bias."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    hits_raw = hits_cup = 0
    est_raw, est_cup, true = [], [], []
    for _ in range(n_sims):
        idx, t = _draw(len(y), n_per_arm, rng)
        yy = y[idx].copy()
        before = yy[t].copy()
        yy[t] = inject_effect(yy[t], effect, cap, rng)
        true.append((yy[t] - before).mean())
        p_raw = welch_p(yy[t], yy[~t])
        d_cup, p_cup = cuped_test(yy, x[idx], t)
        hits_raw += p_raw < alpha
        hits_cup += p_cup < alpha
        est_raw.append(yy[t].mean() - yy[~t].mean())
        est_cup.append(d_cup)
    return {
        "power_raw": hits_raw / n_sims,
        "power_cuped": hits_cup / n_sims,
        "true_effect": float(np.mean(true)),
        "mean_estimate_raw": float(np.mean(est_raw)),
        "mean_estimate_cuped": float(np.mean(est_cup)),
        "sd_estimate_raw": float(np.std(est_raw)),
        "sd_estimate_cuped": float(np.std(est_cup)),
    }


def peeking_simulation(daily, n_per_arm, n_sims=2000, alpha=0.05, seed=0):
    """A/A tests on real day-by-day activity, checked every day.

    `daily` is players x test-days (1 = active). Each day the running total of
    active days is compared between arms. Returns the false-positive rate when
    stopping at the first p < alpha versus testing once at the end.
    """
    rng = np.random.default_rng(seed)
    daily = np.asarray(daily, dtype=float)
    n_days = daily.shape[1]
    any_sig = end_sig = 0
    first_sig_day = []
    for _ in range(n_sims):
        idx, t = _draw(len(daily), n_per_arm, rng)
        cum = np.cumsum(daily[idx], axis=1)
        a, b = cum[t], cum[~t]
        ma, mb = a.mean(axis=0), b.mean(axis=0)
        va, vb = a.var(axis=0, ddof=1), b.var(axis=0, ddof=1)
        se = np.sqrt(va / len(a) + vb / len(b))
        with np.errstate(divide="ignore", invalid="ignore"):
            z = np.where(se > 0, (ma - mb) / se, 0.0)
        p = 2 * stats.norm.sf(np.abs(z))
        sig = p < alpha
        if sig.any():
            any_sig += 1
            first_sig_day.append(int(np.argmax(sig)) + 1)
        end_sig += sig[n_days - 1]
    return {
        "false_positive_peeking": any_sig / n_sims,
        "false_positive_fixed": end_sig / n_sims,
        "median_first_false_alarm_day": float(np.median(first_sig_day)) if first_sig_day else None,
    }
