import numpy as np
import pandas as pd

from core.reference import MAX_LOSS

RISK_REF = 20.0        # demande pour laquelle le score sature à 100
BLOCK_THRESHOLD = 60   # score à partir duquel on bloque l'irrigation


def vpd_kpa(temp_c, rh_pct):
    """Déficit de pression de vapeur (kPa), formule de Tetens."""
    es = 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))
    return es * (1 - rh_pct / 100)


def level(score: float) -> str:
    if score < 25:
        return "Faible"
    if score < 50:
        return "Modéré"
    if score < 75:
        return "Élevé"
    return "Extrême"


def compute_risk(hourly: pd.DataFrame) -> pd.DataFrame:
    """Risque d'évaporation heure par heure sur les 48 prochaines heures."""
    now = pd.Timestamp.now(tz="Africa/Casablanca").floor("h").tz_localize(None)
    df = hourly[hourly["time"] >= now].head(48).reset_index(drop=True)
    df["vpd_kpa"] = vpd_kpa(df["temp"], df["humidite"])
    df["demande"] = (1 + 0.5 * df["vent_ms"]) * df["vpd_kpa"]
    df["risque"] = (df["demande"] / RISK_REF * 100).clip(0, 100).round(0)
    df["chergui"] = (
        df["dir_vent"].between(45, 135)
        & (df["temp"] >= 30)
        & (df["humidite"] <= 30)
        & (df["vent_ms"] >= 4)
    )
    return df


def best_windows(df: pd.DataFrame, duration_h: int = 3, top: int = 3) -> list:
    """Créneaux consécutifs de durée donnée au risque moyen le plus bas (sans chevauchement)."""
    if len(df) < duration_h:
        return []
    means = df["risque"].rolling(duration_h).mean().shift(-(duration_h - 1))
    candidates = sorted((means.iloc[i], i) for i in range(len(df) - duration_h + 1))
    chosen = []
    for m, i in candidates:
        if all(abs(i - j) >= duration_h for _, j in chosen):
            chosen.append((m, i))
        if len(chosen) == top:
            break
    return [
        {
            "debut": df["time"].iloc[i],
            "fin": df["time"].iloc[i + duration_h - 1] + pd.Timedelta(hours=1),
            "risque_moyen": float(round(m, 0)),
        }
        for m, i in chosen
    ]


def shield_status(df: pd.DataFrame, irrigation: str, duration_h: int = 3) -> dict:
    max_loss = MAX_LOSS[irrigation]
    windows = best_windows(df.head(24), duration_h)  # créneaux utiles : prochaines 24 h
    risk_now = float(df.loc[0, "risque"])
    risk_soon = float(df.head(3)["risque"].max())  # maintenant + 2 prochaines heures
    blocked = risk_soon >= BLOCK_THRESHOLD

    chergui_hours = df[df["chergui"]].head(1)
    chergui_at = chergui_hours["time"].iloc[0] if not chergui_hours.empty else None

    loss_now = max_loss * max(risk_now, risk_soon) / 100
    loss_best = max_loss * windows[0]["risque_moyen"] / 100 if windows else None

    message = "Conditions acceptables : vous pouvez irriguer maintenant."
    if windows:
        best = windows[0]
        slot = f"{best['debut']:%Hh%M} à {best['fin']:%Hh%M}"
        if blocked:
            message = (
                f"Alerte évaporation maximale : repoussez l'irrigation au créneau {slot}. "
                f"Pertes estimées : {loss_now:.0f} % maintenant contre {loss_best:.0f} % sur ce créneau."
            )
        else:
            message += f" Meilleur créneau des 24 h : {slot} (risque moyen {best['risque_moyen']:.0f}/100)."

    return {
        "risque_now": risk_now,
        "niveau": level(risk_now),
        "bloque": blocked,
        "chergui_at": chergui_at,
        "fenetres": windows,
        "message": message,
        "perte_now": loss_now,
        "perte_best": loss_best,
        "max_loss": max_loss,
    }