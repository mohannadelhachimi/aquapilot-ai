# Coordonnées utilisées plus tard pour appeler NASA POWER
PROVINCES = {
    "Dakhla": {"lat": 23.6848, "lon": -15.9570},
    "Laâyoune": {"lat": 27.1253, "lon": -13.1625},
    "Guelmim": {"lat": 28.9870, "lon": -10.0574},
}

# Kc par stade (FAO-56) et tolérance au sel (FAO-29 : seuil de CE du sol, pente de perte de rendement).
# Valeurs indicatives, à vérifier dans les tableaux FAO avant la présentation finale.
CROPS = {
    "Tomate":         {"kc_ini": 0.60, "kc_mid": 1.15, "kc_end": 0.80, "stades": (30, 40, 40, 25), "ece_seuil": 2.5, "pente": 9.9},
    "Poivron":        {"kc_ini": 0.60, "kc_mid": 1.05, "kc_end": 0.90, "stades": (30, 35, 40, 20), "ece_seuil": 1.5, "pente": 14.0},
    "Melon":          {"kc_ini": 0.50, "kc_mid": 1.05, "kc_end": 0.75, "stades": (25, 35, 40, 20), "ece_seuil": 2.2, "pente": 7.3},
    "Pastèque":       {"kc_ini": 0.40, "kc_mid": 1.00, "kc_end": 0.75, "stades": (20, 30, 30, 30), "ece_seuil": 2.2, "pente": 20.0},
    "Courgette":      {"kc_ini": 0.50, "kc_mid": 0.95, "kc_end": 0.75, "stades": (25, 35, 25, 15), "ece_seuil": 4.7, "pente": 9.4},
    "Pomme de terre": {"kc_ini": 0.50, "kc_mid": 1.15, "kc_end": 0.75, "stades": (25, 30, 45, 30), "ece_seuil": 1.7, "pente": 12.0},
}

# Rendement d'irrigation
IRRIGATION = {
    "Goutte-à-goutte": 0.90,
    "Aspersion": 0.75,
    "Gravitaire": 0.60,
}

WATER_SOURCES = ["Eau dessalée", "Nappe souterraine", "Mélange dessalée + nappe"]

# Perte maximale par évaporation/dérive dans les pires conditions (hypothèses du modèle,
# à calibrer avec la littérature ou des mesures terrain)
MAX_LOSS = {
    "Goutte-à-goutte": 5,
    "Aspersion": 25,
    "Gravitaire": 15,
}

# Hypothèses du Nexus Eau-Énergie (à remplacer par des valeurs sourcées)
BASE_TARIFF_MAD_KWH = 1.20   # valeur PROVISOIRE
PUMP_HEAD_M = 60             # hauteur manométrique totale du pompage (m)
PUMP_EFFICIENCY = 0.60       # rendement global motopompe

# Profondeur racinaire effective (m), valeurs indicatives (FAO-56)
ROOT_DEPTH_M = {
    "Tomate": 0.7, "Poivron": 0.6, "Melon": 0.8,
    "Pastèque": 0.9, "Courgette": 0.6, "Pomme de terre": 0.5,
}