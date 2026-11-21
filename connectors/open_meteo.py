import pandas as pd
import requests

URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_RENAME = {
    "temperature_2m": "temp",
    "relative_humidity_2m": "humidite",
    "wind_speed_10m": "vent_ms",
    "shortwave_radiation": "rayonnement_wm2",
    "precipitation": "pluie_mm",
}
DAILY_RENAME = {
    "et0_fao_evapotranspiration": "et0_mm",
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum": "pluie_mm",
}


def fetch_forecast(lat: float, lon: float, days: int = 7):
    """Retourne (prévisions horaires, prévisions journalières)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_RENAME),
        "daily": ",".join(DAILY_RENAME),
        "wind_speed_unit": "ms",
        "timezone": "Africa/Casablanca",
        "forecast_days": days,
    }
    response = requests.get(URL, params=params, timeout=30)
    response.raise_for_status()
    js = response.json()

    hourly = pd.DataFrame(js["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"])
    hourly = hourly.rename(columns=HOURLY_RENAME)

    daily = pd.DataFrame(js["daily"])
    daily["time"] = pd.to_datetime(daily["time"])
    daily = daily.rename(columns=DAILY_RENAME)
    return hourly, daily

HOURLY_RENAME = {
    "temperature_2m": "temp",
    "relative_humidity_2m": "humidite",
    "wind_speed_10m": "vent_ms",
    "wind_direction_10m": "dir_vent",
    "shortwave_radiation": "rayonnement_wm2",
    "precipitation": "pluie_mm",
    "wind_speed_100m": "vent100_ms",
}