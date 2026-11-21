from math import asin, cos, radians, sin, sqrt


def distance_km(lat1, lon1, lat2, lon2):
    """Distance à vol d'oiseau entre deux points (formule de Haversine)."""
    r = 6371
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))