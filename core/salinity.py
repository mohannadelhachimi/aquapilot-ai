from datetime import date, timedelta

import numpy as np
import pandas as pd

from core.agro import effective_rain, kc_for_day
from core.reference import CROPS, IRRIGATION, ROOT_DEPTH_M

# Hypothèses du modèle : ordres de grandeur, à valider avec une source agronomique (FAO-29, INRA)
THETA_FC = 0.20           # humidité à la capacité au champ (sol limoneux)
ECE_PER_ECSW = 0.5        # ECe ≈ 0,5 × CE de la solution du sol à la capacité au champ
G_PER_L_PER_DSM = 0.64    # 1 dS/m ≈ 640 mg/L de sels dissous (FAO)
DRAIN_CONC_FACTOR = 2.5   # concentration drainée / concentration moyenne racinaire
MIX_EFF = 0.7             # efficacité d'un lessivage de remise en état
LF_MAX = 0.4              # au-delà, l'eau est jugée inadaptée à la culture
TARGET_FACTOR = 0.6       # objectif de fin de saison : 60 % du seuil de la culture


def root_water_mm(crop: str) -> float:
    return THETA_FC * ROOT_DEPTH_M[crop] * 1000


def ece_from_salt(salt: float, w: float) -> float:
    return ECE_PER_ECSW * (salt / w) / G_PER_L_PER_DSM


def salt_from_ece(ece: float, w: float) -> float:
    return ece / ECE_PER_ECSW * G_PER_L_PER_DSM * w


def leaching_requirement(ec_w: float, ece_thr: float):
    """Besoin de lessivage FAO-29 : LR = ECw / (5·ECe_seuil − ECw). None si impossible."""
    denom = 5 * ece_thr - ec_w
    return None if denom <= 0 else ec_w / denom


def recommended_lf(ec_w: float, ece_thr: float):
    """Retourne (fraction de lessivage recommandée, eau inadaptée ?)."""
    lr = leaching_requirement(ec_w, ece_thr)
    if lr is None:
        return LF_MAX, True
    return float(min(max(lr, 0.05), LF_MAX)), lr > LF_MAX


def simulate_season(farm: dict, clim: pd.DataFrame, lf: float = 0.0, ece0: float = 1.5) -> pd.DataFrame:
    crop = farm["crop"]
    cdata = CROPS[crop]
    w = root_water_mm(crop)
    eff = IRRIGATION[farm["irrigation"]]
    start = date.fromisoformat(farm["planting_date"])
    salt = salt_from_ece(ece0, w)

    rows = []
    for k in range(sum(cdata["stades"])):
        day = start + timedelta(days=k)
        doy = min(day.timetuple().tm_yday, 366)
        et0, rain = float(clim.loc[doy, "et0_mm"]), float(clim.loc[doy, "pluie_mm"])
        kc, _ = kc_for_day(crop, k)
        etc = et0 * kc
        p_eff = effective_rain(rain)

        net = max(0.0, etc - p_eff)
        irr = net / (1 - lf)                                   # eau arrivant au sol (mm)
        drain = lf * irr + max(0.0, p_eff - etc)

        c_soil = salt / w
        salt_out = min(salt, drain * DRAIN_CONC_FACTOR * c_soil)
        salt = salt + irr * farm["ec_water"] * G_PER_L_PER_DSM - salt_out

        rows.append({
            "date": day, "jour": k, "etc_mm": etc, "irrig_sol_mm": irr, "drainage_mm": drain,
            "ece": ece_from_salt(salt, w),
            "volume_m3": irr / eff * farm["area_ha"] * 10,
        })
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame, farm: dict) -> dict:
    c = CROPS[farm["crop"]]
    thr = c["ece_seuil"]
    ece_mean = float(df["ece"].mean())
    loss = min(100.0, max(0.0, c["pente"] * (ece_mean - thr)))
    above = df[df["ece"] >= 0.8 * thr]
    return {
        "ece_fin": float(df["ece"].iloc[-1]),
        "ece_moy": ece_mean,
        "ece_max": float(df["ece"].max()),
        "perte_pct": float(loss),
        "volume_m3": float(df["volume_m3"].sum()),
        "jour_alerte": int(above["jour"].iloc[0]) if not above.empty else None,
        "perte_suivante_pct": float(min(100.0, max(0.0, c["pente"] * (df["ece"].iloc[-1] - thr)))),
    }


def compare_scenarios(farm: dict, clim: pd.DataFrame, ece0: float = 1.5):
    thr = CROPS[farm["crop"]]["ece_seuil"]
    lf_rec, unsuitable = recommended_lf(farm["ec_water"], thr)
    renforce = min(LF_MAX, lf_rec * 1.5)
    scenarios = {"Sans lessivage": 0.0, "Lessivage recommandé": lf_rec}
    if renforce > lf_rec + 1e-9:
        scenarios["Lessivage renforcé"] = renforce
    rows, sims, summ, base_vol = [], {}, {}, None
    for name, lf in scenarios.items():
        df = simulate_season(farm, clim, lf, ece0)
        s = summarize(df, farm)
        base_vol = s["volume_m3"] if base_vol is None else base_vol
        sims[name], summ[name] = df, s
        rows.append({
            "Scénario": name,
            "Lessivage (%)": round(lf * 100, 1),
            "CE sol fin de saison (dS/m)": round(s["ece_fin"], 2),
            "CE sol moyenne (dS/m)": round(s["ece_moy"], 2),
            "Perte de rendement (%)": round(s["perte_pct"], 1),
            "Volume saison (m³)": round(s["volume_m3"]),
            "Eau supplémentaire (m³)": round(s["volume_m3"] - base_vol),
        })
    return pd.DataFrame(rows), sims, summ, lf_rec, unsuitable


def flush_plan(farm: dict, ece_from: float) -> dict:
    """Lessivage de remise en état pour ramener la CE du sol à l'objectif (60 % du seuil)."""
    target = TARGET_FACTOR * CROPS[farm["crop"]]["ece_seuil"]
    if ece_from <= target:
        return {"necessaire": False, "cible": target, "mm": 0.0, "m3": 0.0}
    mm = root_water_mm(farm["crop"]) * np.log(ece_from / target) / MIX_EFF
    return {"necessaire": True, "cible": target, "mm": float(mm), "m3": float(mm * farm["area_ha"] * 10)}


def recommendations(farm: dict, summ: dict, ece0: float, lf_rec: float, unsuitable: bool) -> dict:
    """Recommandations en trois phases : début, pendant et fin de saison."""
    thr = CROPS[farm["crop"]]["ece_seuil"]
    none, rec = summ["Sans lessivage"], summ["Lessivage recommandé"]
    pre, during, post = [], [], []

    f0 = flush_plan(farm, ece0)
    if f0["necessaire"]:
        pre.append(f"Sol déjà salin (CE {ece0:.1f} dS/m, seuil de la culture {thr}) : lessivage avant plantation "
                   f"d'environ {f0['mm']:.0f} mm ({f0['m3']:.0f} m³), avec l'eau la moins salée disponible.")
    else:
        pre.append("Salinité initiale acceptable : pas de lessivage préalable nécessaire.")
    tolerant = [n for n, v in CROPS.items() if v["ece_seuil"] > thr]
    if unsuitable:
        pre.append("Eau trop salée pour cette culture, même avec lessivage : la mélanger avec de l'eau dessalée "
                   f"ou changer de culture (plus tolérantes : {', '.join(tolerant) or 'aucune dans la liste'}).")
    elif none["perte_pct"] >= 10 and tolerant:
        pre.append(f"Risque marqué sans lessivage : envisager une culture plus tolérante ({', '.join(tolerant)}).")
    if farm["irrigation"] == "Aspersion" and farm["ec_water"] >= 2:
        pre.append("Avec une eau chargée en sel, l'aspersion mouille le feuillage (risque de brûlures) : "
                   "préférer le goutte-à-goutte.")
    pre.append("Pratiques de préparation : paillage pour limiter l'évaporation et la remontée de sel, "
               "apport de matière organique pour améliorer la structure du sol.")

    during.append(f"Viser une fraction de lessivage d'environ {lf_rec * 100:.0f} %, apportée par un arrosage "
                  "complémentaire périodique (par exemple une irrigation par semaine) plutôt qu'à chaque arrosage.")
    if none["jour_alerte"] is not None:
        during.append(f"Sans lessivage, le seuil d'alerte (80 % du seuil de la culture) serait atteint vers le "
                      f"jour {none['jour_alerte']} du cycle : mesurer la CE du sol avant cette date.")
    during.append("Irriguer aux créneaux d'Evapo-Shield : moins d'évaporation, donc moins de sel remontant en surface.")
    if farm["water_source"] != "Eau dessalée":
        during.append("Diluer l'eau de nappe avec de l'eau dessalée lorsque c'est possible.")

    f1 = flush_plan(farm, rec["ece_fin"])
    if f1["necessaire"]:
        post.append(f"Lessivage de remise en état entre deux cycles : environ {f1['mm']:.0f} mm "
                    f"({f1['m3']:.0f} m³) pour ramener la CE du sol à {f1['cible']:.1f} dS/m, "
                    "idéalement en saison à faible évapotranspiration et avec l'eau la moins salée.")
    else:
        post.append("CE du sol en fin de saison sous l'objectif : pas de lessivage de remise en état nécessaire.")
    post.append("Mesurer la CE du sol à deux profondeurs avant de replanter.")
    if farm["water_source"] != "Eau dessalée":
        post.append("Eau de nappe : contrôler la sodicité (SAR) ; un apport de gypse peut être nécessaire.")
    post.append("Alterner avec une culture plus tolérante ou un engrais vert pour la saison suivante.")
    return {"Début de saison": pre, "Pendant la saison": during, "Fin de saison": post}