import hashlib


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# Comptes de démonstration (en production : base de données + mots de passe hachés avec sel)
USERS = {
    "admin": {
        "password_hash": _hash("admin123"),
        "role": "admin",
        "name": "Administration régionale",
    },
    "ferme1": {
        "password_hash": _hash("demo123"),
        "role": "agriculteur",
        "name": "Ferme Atlantique",
        "province": "Dakhla",
    },
    "ferme2": {
        "password_hash": _hash("demo123"),
        "role": "agriculteur",
        "name": "Ferme Saguia",
        "province": "Laâyoune",
    },
}


def authenticate(username: str, password: str):
    """Retourne le profil de l'utilisateur si les identifiants sont valides, sinon None."""
    user = USERS.get(username.strip().lower())
    if user and user["password_hash"] == _hash(password):
        return {"username": username.strip().lower(), **{k: v for k, v in user.items() if k != "password_hash"}}
    return None