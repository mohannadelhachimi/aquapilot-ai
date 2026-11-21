import numpy as np
import pandas as pd

from core.evapo import BLOCK_THRESHOLD
from core.reference import BASE_TARIFF_MAD_KWH, PUMP_EFFICIENCY, PUMP_HEAD_M

SOLAR_REF = 900.0                  # W/m² : rayonnement de référence (indice = 1)
CUT_IN, RATED, CUT_OUT = 3.0, 12.0, 25.0   # m/s, courbe de puissance éolienne simplifiée


def wind_index(v):
    v = np.asarray(v, dtype=float)
    idx = np.clip((v - CUT_IN) / (RATED - CUT_IN), 0, 1) ** 3
    return np.where(v >= CUT_OUT, 0.0, idx)


def energy_kwh_per_m3() -> float:
    """Énergie de pompage : rho*g*H / rendement (3,6e6 J = 1 kWh)."""
    return 1000 * 9.81 * PUMP_HEAD_M / 3.6e6 / PUMP_EFFICIENCY


def add_energy_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["solaire_idx"] = (out["rayonnement_wm2"] / SOLAR_REF).clip(0, 1)
    out["eolien_idx"] = wind_index(out["vent100_ms"])
    out["enr_idx"] = 0.5 * out["solaire_idx"] + 0.5 * out["eolien_idx"]
    out["prix_mad_kwh"] = BASE_TARIFF_MAD_KWH * (1.25 - 0.5 * out["enr_idx"])
    return out


def nexus_plan(df: pd.DataFrame, volume_m3: float, duration_h: int = 3):
    """Cherche le créneau de pompage le moins cher, compatible avec Evapo-Shield."""
    d = add_energy_columns(df.head(24)).reset_index(drop=True)
    rows = []
    for i in range(len(d) - duration_h + 1):
        w = d.iloc[i:i + duration_h]
        rows.append({
            "debut": w["time"].iloc[0],
            "fin": w["time"].iloc[-1] + pd.Timedelta(hours=1),
            "risque_max": float(w["risque"].max()),
            "prix": float(w["prix_mad_kwh"].mean()),
            "enr": float(w["enr_idx"].mean()),
        })
    slots = pd.DataFrame(rows)
    kwh = volume_m3 * energy_kwh_per_m3()
    slots["cout_mad"] = slots["prix"] * kwh

    allowed = slots[slots["risque_max"] < BLOCK_THRESHOLD]
    ref = slots.iloc[0]  # référence : pomper dès maintenant
    if allowed.empty:
        return {"horaire": d, "best": None, "ref": ref, "kwh": kwh}

    best = allowed.sort_values("cout_mad").iloc[0]
    saving_mad = float(ref["cout_mad"] - best["cout_mad"])
    saving_pct = saving_mad / ref["cout_mad"] * 100 if ref["cout_mad"] > 0 else 0.0
    return {
        "horaire": d, "best": best, "ref": ref, "kwh": kwh,
        "saving_mad": max(saving_mad, 0.0), "saving_pct": max(saving_pct, 0.0),
    }

def regional_nexus(profile: pd.Series, risk_df: pd.DataFrame, flex_share: float = 0.3, top_hours: int = 6) -> dict:
    """Alignement demande de pompage / énergie renouvelable, et scénario de pompage vert pour une province.

    profile : demande horaire typique (m³/h) indexée par heure 0..23
    risk_df : sortie de compute_risk (prévisions horaires avec risque d'évaporation)
    """
    d = add_energy_columns(risk_df.head(24)).reset_index(drop=True)
    d["h"] = d["time"].dt.hour
    d = d.set_index("h")
    kwh_m3 = energy_kwh_per_m3()

    base = profile.reindex(d.index).fillna(0.0)
    flex = base * flex_share
    scen = base - flex

    allowed = d[d["risque"] < BLOCK_THRESHOLD]
    chosen = list(allowed.sort_values("prix_mad_kwh").head(top_hours).index)
    if chosen:
        scen[chosen] = scen[chosen] + flex.sum() / len(chosen)
    else:
        scen = base.copy()

    def metrics(vol):
        kwh = vol * kwh_m3
        total = vol.sum()
        return {
            "volume": float(total),
            "kwh": float(kwh.sum()),
            "cout": float((kwh * d["prix_mad_kwh"]).sum()),
            "alignement": float((vol * d["enr_idx"]).sum() / total * 100) if total > 0 else 0.0,
        }

    detail = pd.DataFrame({
        "actuel": base, "pompage_vert": scen,
        "enr_idx": d["enr_idx"], "prix": d["prix_mad_kwh"], "risque": d["risque"],
    })
    return {
        "detail": detail,
        "now": metrics(base),
        "scen": metrics(scen),
        "reference": float(d["enr_idx"].mean() * 100),
        "heures": sorted(chosen),
        "kwh_deplaces": float(flex.sum() * kwh_m3) if chosen else 0.0,
    }