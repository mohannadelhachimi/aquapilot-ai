import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

FEATURES = ["ratio_nuit", "pic_ratio", "vs_med14"]

def daily_features(hourly: pd.DataFrame) -> pd.DataFrame:
    df = hourly.copy()
    if "fuite_reelle" not in df:          # données réelles : pas d'étiquette
        df["fuite_reelle"] = 0
    if "type_evenement" not in df:
        df["type_evenement"] = ""
    df["type_evenement"] = df["type_evenement"].fillna("")
    df["date"] = df["time"].dt.normalize()
    df["h"] = df["time"].dt.hour
    keys = ["farm_id", "date"]

    d = df.groupby(keys).agg(
        volume_m3=("conso_m3", "sum"),
        pic_m3=("conso_m3", "max"),
        heures_fuite=("fuite_reelle", "sum"),
    ).reset_index()
    night = (df[df["h"] <= 4].groupby(keys)["conso_m3"].sum()
             .rename("volume_nuit_m3").reset_index())
    kind = (df[df["type_evenement"] != ""].groupby(keys)["type_evenement"]
            .agg(lambda s: s.mode().iloc[0]).reset_index())
    d = d.merge(night, on=keys).merge(kind, on=keys, how="left")
    d["type_evenement"] = d["type_evenement"].fillna("")
    d = d.sort_values(keys).reset_index(drop=True)

    d["ratio_nuit"] = d["volume_nuit_m3"] / d["volume_m3"]
    d["pic_ratio"] = d["pic_m3"] / (d["volume_m3"] / 24)
    med = d.groupby("farm_id")["volume_m3"].transform(
        lambda s: s.rolling(14, min_periods=5).median().shift(1))
    d["vs_med14"] = (d["volume_m3"] / med).fillna(1.0)
    d["fuite_reelle"] = (d["heures_fuite"] >= 3).astype(int)  # vérité terrain, pour l'évaluation seulement
    return d


def detect(d: pd.DataFrame, contamination: float = 0.03, seed: int = 42) -> pd.DataFrame:
    """Isolation Forest non supervisé : il ne voit jamais la colonne fuite_reelle."""
    model = IsolationForest(n_estimators=300, contamination=contamination, random_state=seed)
    model.fit(d[FEATURES])
    out = d.copy()
    out["score"] = -model.score_samples(d[FEATURES])      # plus haut = plus anormal
    out["anomalie"] = (model.predict(d[FEATURES]) == -1).astype(int)
    return out


def diagnose(row, night_ref: float) -> str:
    if row["pic_ratio"] > 4.0:
        return "Rupture ou pic anormal"
    if row["ratio_nuit"] > 2 * night_ref:
        return "Fuite probable (débit nocturne élevé)"
    if row["vs_med14"] > 1.4:
        return "Surconsommation"
    return "Comportement atypique"


def evaluate(d: pd.DataFrame) -> dict:
    y, p = d["fuite_reelle"], d["anomalie"]
    tn, fp, fn, tp = confusion_matrix(y, p, labels=[0, 1]).ravel()
    return {
        "precision": precision_score(y, p, zero_division=0),
        "rappel": recall_score(y, p, zero_division=0),
        "f1": f1_score(y, p, zero_division=0),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
    }