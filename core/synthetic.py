from pathlib import Path

import numpy as np
import pandas as pd

from core.reference import CROPS, PROVINCES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CODES = {"Dakhla": "DAK", "Laâyoune": "LAY", "Guelmim": "GUE"}

# Profil horaire d'irrigation (matin et fin d'après-midi), normalisé
PROFILE = np.array([0.1, 0.1, 0.1, 0.1, 0.2, 0.6, 2.0, 3.0, 3.0, 2.0, 1.0, 0.5,
                    0.3, 0.3, 0.3, 0.4, 0.8, 2.0, 3.0, 3.0, 2.0, 0.8, 0.3, 0.1])
PROFILE = PROFILE / PROFILE.sum()

BASE_M3_HA_DAY = 60  # consommation moyenne simulée (m³/ha/jour), hypothèse


def make_farms(per_province: int = 4, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for prov, c in PROVINCES.items():
        for k in range(per_province):
            rows.append({
                "farm_id": f"{CODES[prov]}-{k + 1:02d}",
                "province": prov,
                "lat": round(c["lat"] + rng.uniform(-0.15, 0.15), 5),
                "lon": round(c["lon"] + rng.uniform(-0.15, 0.15), 5),
                "crop": str(rng.choice(list(CROPS))),
                "area_ha": round(float(rng.uniform(1, 12)), 1),
            })
    return pd.DataFrame(rows)
# Événements forcés pour garantir une démo variée (en plus des tirages aléatoires)
# Événements forcés pour garantir une démo variée (en plus des tirages aléatoires)
FORCED = {
    "DAK-01": ["rupture"],
    "DAK-03": ["surconsommation"],
    "LAY-02": ["rupture", "rupture"],
    "GUE-02": ["surconsommation"],
}


def _free_slot(label, length, lo, hi, rng, tries=30):
    """Début aléatoire d'un événement dans une zone encore libre (pas de chevauchement)."""
    for _ in range(tries):
        s = int(rng.integers(lo, hi))
        if not label[s:s + length].any():
            return s
    return None


def generate(days: int = 180, seed: int = 42):
    """Consommation horaire simulée + événements injectés (avec étiquettes)."""
    rng = np.random.default_rng(seed)
    farms = make_farms(seed=seed)

    start = pd.Timestamp.today().normalize() - pd.Timedelta(days=days)
    times = pd.date_range(start, periods=days * 24, freq="h")
    n = len(times)
    hours = times.hour.to_numpy()
    doy = times.dayofyear.to_numpy()
    day_idx = (times.normalize() - start).days.to_numpy()
    seasonal = 1 + 0.35 * np.sin(2 * np.pi * (doy - 110) / 365)

    frames = []
    for _, f in farms.iterrows():
        day_factor = rng.lognormal(0, 0.10, days)
        hour_noise = rng.lognormal(0, 0.12, n)
        base = f["area_ha"] * BASE_M3_HA_DAY * seasonal * PROFILE[hours] * day_factor[day_idx] * hour_noise

        conso = base.copy()
        label = np.zeros(n, dtype=int)
        kinds = np.full(n, "", dtype=object)
        mean_hourly = base.mean()

        def inject(kind):
            if kind == "fuite":
                length = int(rng.integers(3, 15)) * 24          # débit constant, 3 à 14 jours
            elif kind == "surconsommation":
                length = int(rng.integers(2, 6)) * 24           # sur-irrigation, 2 à 5 jours
            else:
                length = 3                                      # rupture : éclatement de 3 h
            s = _free_slot(label, length, 14 * 24, n - length, rng)
            if s is None:
                return
            if kind == "fuite":
                conso[s:s + length] += mean_hourly * rng.uniform(0.15, 0.6)
            elif kind == "surconsommation":
                conso[s:s + length] *= rng.uniform(1.6, 2.2)
            else:
                conso[s:s + length] += mean_hourly * rng.uniform(12, 20)
            label[s:s + length] = 1
            kinds[s:s + length] = kind

        events = ["fuite"] * int(rng.choice([0, 1, 2], p=[0.5, 0.4, 0.1]))
        if rng.random() < 0.15:
            events.append("rupture")
        if rng.random() < 0.25:
            events.append("surconsommation")
        events += FORCED.get(f["farm_id"], [])
        for e in events:
            inject(e)

        frames.append(pd.DataFrame({
            "farm_id": f["farm_id"], "time": times,
            "conso_m3": conso.round(3), "fuite_reelle": label, "type_evenement": kinds,
        }))
    return pd.concat(frames, ignore_index=True), farms

def ensure_data(force: bool = False):
    """Charge les CSV, ou les génère s'ils n'existent pas encore."""
    h, f = DATA_DIR / "conso_horaire.csv", DATA_DIR / "fermes_simulees.csv"
    if force or not (h.exists() and f.exists()):
        hourly, farms = generate()
        DATA_DIR.mkdir(exist_ok=True)
        hourly.to_csv(h, index=False)
        farms.to_csv(f, index=False)
    return pd.read_csv(h, parse_dates=["time"]), pd.read_csv(f)