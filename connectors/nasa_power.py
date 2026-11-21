import numpy as np
import pandas as pd
import requests

BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = "T2M,T2M_MAX,T2M_MIN,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR"

RENAME = {
    "T2M": "temp_moy",
    "T2M_MAX": "temp_max",
    "T2M_MIN": "temp_min",
    "RH2M": "humidite",
    "WS2M": "vent_ms",
    "ALLSKY_SFC_SW_DWN": "rayonnement_mj",
    "PRECTOTCORR": "pluie_mm",
}


def fetch_daily(lat: float, lon: float, start, end) -> pd.DataFrame:
    """Météo journalière observée (NASA POWER). start/end : objets date."""
    params = {
        "parameters": PARAMETERS,
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    response = requests.get(BASE_URL, params=params, timeout=40)
    response.raise_for_status()
    data = response.json()["properties"]["parameter"]

    df = pd.DataFrame(data).rename(columns=RENAME)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    return df.replace(-999, np.nan)  # -999 = valeur manquante chez NASA POWER