import numpy as np
import pandas as pd

NIGHT_HOURS = [22, 23, 0, 1, 2, 3, 4, 5]   # heures à faible évaporation, cohérent avec Evapo-Shield


def _fmt(x) -> str:
    return f"{abs(x):,.0f}".replace(",", " ")


def explain(r) -> str:
    anom_pct = r["part_anomalies"] / r["volume_prev"] * 100 if r["volume_prev"] else 0.0

    if anom_pct >= 3:
        if r["var_m3"] > 0:
            share = r["part_anomalies"] / r["var_m3"]
            word = "surtout" if share > 0.5 else "en partie"
            return f"Hausse due {word} à des anomalies détectées (+{_fmt(r['part_anomalies'])} m³)"
        return f"Anomalies détectées (+{_fmt(r['part_anomalies'])} m³) masquées par la baisse saisonnière"
    if anom_pct <= -3:
        return f"Baisse en partie due à la fin d'une anomalie de la période précédente (−{_fmt(r['part_anomalies'])} m³)"
    if abs(r["var_pct"]) < 5:
        return "Consommation stable"
    if r["var_m3"] > 0:
        return "Hausse liée à la variation normale (saison, climat, culture)"
    return "Baisse liée à la variation normale (saison, climat, culture)"


def period_comparison(daily: pd.DataFrame, days: int = 30) -> pd.DataFrame:
    """Compare les `days` derniers jours aux `days` jours précédents, ferme par ferme."""
    d = daily.copy()
    last = d["date"].max()
    cur_start = last - pd.Timedelta(days=days - 1)
    prev_start = cur_start - pd.Timedelta(days=days)

    base = d["volume_m3"] / d["vs_med14"]            # volume attendu d'après les 14 jours précédents
    d["excess"] = np.where(d["anomalie"] == 1, (d["volume_m3"] - base).clip(lower=0), 0.0)

    def agg(x):
        return x.groupby("farm_id").agg(
            volume=("volume_m3", "sum"), excess=("excess", "sum"), nuit=("volume_nuit_m3", "sum"))

    cur = agg(d[d["date"] >= cur_start])
    prev = agg(d[(d["date"] >= prev_start) & (d["date"] < cur_start)])
    out = cur.join(prev, lsuffix="_cur", rsuffix="_prev", how="inner").reset_index()

    out["var_m3"] = out["volume_cur"] - out["volume_prev"]
    out["var_pct"] = out["var_m3"] / out["volume_prev"] * 100
    out["part_anomalies"] = out["excess_cur"] - out["excess_prev"]
    out["part_normale"] = out["var_m3"] - out["part_anomalies"]
    out["nuit_cur_pct"] = out["nuit_cur"] / out["volume_cur"] * 100
    out["nuit_prev_pct"] = out["nuit_prev"] / out["volume_prev"] * 100
    out["explication"] = out.apply(explain, axis=1)
    return out


def regional_profile(hourly: pd.DataFrame, farm_ids) -> pd.Series:
    """Charge horaire médiane (m³/h) de l'ensemble des fermes données : robuste aux jours anormaux."""
    h = hourly[hourly["farm_id"].isin(farm_ids)]
    total = h.groupby([h["time"].dt.normalize().rename("date"), h["time"].dt.hour.rename("h")])["conso_m3"].sum()
    return total.groupby("h").median()


def peak_stats(profile: pd.Series) -> dict:
    return {
        "heure_pointe": int(profile.idxmax()),
        "pic": float(profile.max()),
        "moyenne": float(profile.mean()),
        "facteur_pointe": float(profile.max() / profile.mean()),
    }


def simultaneity(hourly: pd.DataFrame, farm_ids) -> pd.Series:
    """Part des fermes en irrigation active à chaque heure (≥ 1,5 × leur propre moyenne horaire)."""
    h = hourly[hourly["farm_id"].isin(farm_ids)]
    prof = h.groupby(["farm_id", h["time"].dt.hour.rename("h")])["conso_m3"].median().unstack()
    active = prof.ge(prof.mean(axis=1) * 1.5, axis=0)
    return active.mean(axis=0)


def shift_scenario(profile: pd.Series, share: float) -> pd.Series:
    """Décale `share` du volume des heures de pointe (quartile haut) vers les heures de nuit. Volume total conservé."""
    peak_hours = profile[profile >= profile.quantile(0.75)].index
    moved = profile[peak_hours].sum() * share
    out = profile.copy()
    out[peak_hours] = profile[peak_hours] * (1 - share)
    out[NIGHT_HOURS] = out[NIGHT_HOURS] + moved / len(NIGHT_HOURS)
    return out