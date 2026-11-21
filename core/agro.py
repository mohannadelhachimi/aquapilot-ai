from datetime import date

import pandas as pd

from core.reference import CROPS, IRRIGATION


def kc_for_day(crop: str, days_since_planting: int):
    """Kc interpolé selon le stade (FAO-56). Retourne (kc, nom du stade)."""
    c = CROPS[crop]
    ini, dev, mid, late = c["stades"]
    d = days_since_planting

    if d < ini:
        return c["kc_ini"], "Initial"
    if d < ini + dev:
        return c["kc_ini"] + (c["kc_mid"] - c["kc_ini"]) * (d - ini) / dev, "Développement"
    if d < ini + dev + mid:
        return c["kc_mid"], "Mi-saison"
    if d < ini + dev + mid + late:
        return c["kc_mid"] + (c["kc_end"] - c["kc_mid"]) * (d - ini - dev - mid) / late, "Fin de saison"
    return c["kc_end"], "Cycle terminé"


def effective_rain(p_mm: float) -> float:
    """Hypothèse simple : pluies < 2 mm perdues, sinon 75 % utilisable."""
    if pd.isna(p_mm) or p_mm < 2:
        return 0.0
    return 0.75 * p_mm


def irrigation_plan(daily: pd.DataFrame, farm: dict) -> pd.DataFrame:
    """Plan journalier : ETc, besoin net/brut (mm) et volume (m³)."""
    planting = date.fromisoformat(farm["planting_date"])
    efficiency = IRRIGATION[farm["irrigation"]]
    rows = []
    for _, r in daily.iterrows():
        day = r["time"].date()
        kc, stage = kc_for_day(farm["crop"], (day - planting).days)
        etc = r["et0_mm"] * kc
        rain = effective_rain(r["pluie_mm"])
        net = max(0.0, etc - rain)
        gross = net / efficiency
        rows.append({
            "date": day,
            "stade": stage,
            "kc": round(kc, 2),
            "et0_mm": round(r["et0_mm"], 2),
            "etc_mm": round(etc, 2),
            "pluie_eff_mm": round(rain, 2),
            "besoin_net_mm": round(net, 2),
            "besoin_brut_mm": round(gross, 2),
            "volume_m3": round(gross * farm["area_ha"] * 10, 1),
            "m3_par_ha": round(gross * 10, 1),
        })
    return pd.DataFrame(rows)


def scenarios(plan: pd.DataFrame, farm: dict) -> pd.DataFrame:
    """Compare le volume hebdomadaire selon le système d'irrigation."""
    net_total = plan["besoin_net_mm"].sum()
    out = pd.DataFrame([
        {"Système": name, "Volume (m³)": round(net_total / eff * farm["area_ha"] * 10, 1)}
        for name, eff in IRRIGATION.items()
    ])
    reference = out["Volume (m³)"].max()  # le système le moins efficace sert de référence
    out["Économie vs référence (%)"] = ((1 - out["Volume (m³)"] / reference) * 100).round(0)
    return out