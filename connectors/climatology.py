import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def fetch_et0_climatology(lat: float, lon: float) -> pd.DataFrame:
    """Année type lissée : et0_mm et pluie_mm par jour de l'année (index 1 à 366). Mise en cache sur disque."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"clim_{lat:.2f}_{lon:.2f}.csv"
    if path.exists():
        return pd.read_csv(path, index_col=0)

    end = date.today() - timedelta(days=7)
    start = end - timedelta(days=364)
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "et0_fao_evapotranspiration,precipitation_sum",
        "timezone": "Africa/Casablanca",
    }
    last_error = None
    for attempt in range(3):
        try:
            r = requests.get(ARCHIVE_URL, params=params, timeout=90)
            r.raise_for_status()
            break
        except requests.RequestException as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    else:
        raise last_error

    df = pd.DataFrame(r.json()["daily"])
    df["time"] = pd.to_datetime(df["time"])
    df = df.rename(columns={"et0_fao_evapotranspiration": "et0_mm", "precipitation_sum": "pluie_mm"})
    clim = df.groupby(df["time"].dt.dayofyear)[["et0_mm", "pluie_mm"]].mean()

    full = clim.reindex(range(1, 367)).interpolate(limit_direction="both")
    ext = pd.concat([full, full, full])                      # lissage circulaire sur l'année
    smooth = ext.rolling(15, center=True, min_periods=1).mean().iloc[366:732]
    smooth.index = range(1, 367)
    smooth = smooth.fillna(0.0)
    smooth.to_csv(path)
    return smooth