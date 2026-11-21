import copy
import json
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path

from core.auth import USERS
from core.synthetic import make_farms
from core.storage import get_farm

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_FILE = DATA_DIR / "bourse.json"

# Hypothèses PROVISOIRES : à remplacer par des valeurs sourcées (autorité de l'eau, tarifs agricoles)
DEFAULT_RULES = {
    "quota_m3_ha_mois": {"Dakhla": 2000, "Laâyoune": 2000, "Guelmim": 2000},
    "prix_ref": 3.0,         # MAD par token (1 token = 1 m³ économisé)
    "prix_plafond": 4.5,     # plafond fixé par l'administration
    "seuil_economie": 0.20,  # économie minimale du quota pour gagner des tokens
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tx(state, **fields):
    tid = state["next_id"]
    state["next_id"] += 1
    state["transactions"].append({"id": tid, "time": _now(), **fields})


def _credit(state, account, qty, note):
    acc = state["accounts"][account]
    acc["balance"] += qty
    _tx(state, type="credit", seller="", buyer=account, qty=qty, price=0.0, province=acc["province"], note=note)

def ensure_account(state, username, province, name=None) -> bool:
    """Crée le compte Bourse d'un agriculteur s'il n'existe pas encore. Retourne True si créé."""
    if username in state["accounts"]:
        return False
    state["accounts"][username] = {"name": name or username, "province": province,
                                   "balance": 0, "closed_months": [], "simulated": False}
    return True


def _seed() -> dict:
    accounts = {}
    for username, u in USERS.items():
        if u.get("role") == "admin":
            continue
        province = u.get("province") or (get_farm(username) or {}).get("province") or "Dakhla"
        accounts[username] = {"name": u.get("name", username), "province": province,
                              "balance": 0, "closed_months": [], "simulated": False}

    farms = make_farms()
    balances = {"DAK-02": 600, "DAK-03": 300, "LAY-02": 800, "LAY-03": 250, "GUE-01": 500, "GUE-04": 400}
    for fid in balances:
        row = farms[farms["farm_id"] == fid].iloc[0]
        accounts[fid] = {"name": f"Ferme {fid}", "province": row["province"],
                         "balance": 0, "closed_months": [], "simulated": True}

    state = {"rules": copy.deepcopy(DEFAULT_RULES), "accounts": accounts,
             "offers": [], "transactions": [], "next_id": 1}
    for fid, bal in balances.items():     # contreparties de démonstration
        _credit(state, fid, bal, "Solde initial de démonstration")
    for fid, qty, price in [("DAK-02", 300, 3.4), ("DAK-03", 150, 3.0), ("LAY-02", 400, 3.2), ("GUE-01", 250, 3.6)]:
        create_offer(state, fid, qty, price)
    return state


def save(state: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load() -> dict:
    if not STATE_FILE.exists():
        save(_seed())
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def reset() -> None:
    save(_seed())


def previous_month(today: date | None = None) -> str:
    today = today or date.today()
    return (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def quota_m3(state: dict, province: str, area_ha: float) -> float:
    return area_ha * state["rules"]["quota_m3_ha_mois"][province]


def simulated_reading(username: str, month: str, quota: float) -> int:
    """Relevé de compteur SIMULÉ (démo) : entre 70 % et 100 % du quota, stable pour un même mois."""
    u = (zlib.crc32(f"{username}{month}".encode()) % 1000) / 1000
    return round(quota * (0.70 + 0.30 * u))


def total_tokens(state: dict) -> int:
    return sum(a["balance"] for a in state["accounts"].values()) + sum(o["qty"] for o in state["offers"])


def close_month(state, username, quota, conso, month):
    acc = state["accounts"][username]
    if month in acc["closed_months"]:
        return False, f"Le mois {month} est déjà clôturé."
    if quota <= 0:
        return False, "Quota invalide."
    acc["closed_months"].append(month)
    saved = quota - conso
    if saved <= 0:
        return True, f"Mois {month} clôturé : dépassement du quota de {-saved:.0f} m³, aucun token."
    pct = saved / quota
    seuil = state["rules"]["seuil_economie"]
    if pct >= seuil:
        tokens = int(saved)
        _credit(state, username, tokens, f"Économie d'eau {month} ({pct * 100:.0f} % du quota)")
        return True, f"Mois {month} clôturé : {pct * 100:.0f} % d'économie, {tokens} tokens crédités."
    return True, (f"Mois {month} clôturé : {pct * 100:.0f} % d'économie, sous le seuil de "
                  f"{seuil * 100:.0f} % : aucun token.")


def create_offer(state, seller, qty, price):
    acc = state["accounts"].get(seller)
    rules = state["rules"]
    qty = int(qty)
    if acc is None:
        return False, "Compte inconnu."
    if qty <= 0:
        return False, "Quantité invalide."
    if qty > acc["balance"]:
        return False, f"Solde insuffisant ({acc['balance']} tokens disponibles)."
    if price <= 0 or price > rules["prix_plafond"]:
        return False, f"Prix refusé : le plafond fixé par l'administration est de {rules['prix_plafond']:.2f} MAD par token."
    acc["balance"] -= qty                      # séquestre
    oid = state["next_id"]
    state["next_id"] += 1
    state["offers"].append({"id": oid, "seller": seller, "province": acc["province"],
                            "qty": qty, "price": round(float(price), 2), "created": _now()})
    return True, f"Offre publiée : {qty} tokens à {price:.2f} MAD."


def cancel_offer(state, offer_id, username):
    offer = next((o for o in state["offers"] if o["id"] == offer_id), None)
    if offer is None:
        return False, "Offre introuvable."
    if offer["seller"] != username:
        return False, "Vous ne pouvez annuler que vos propres offres."
    state["accounts"][username]["balance"] += offer["qty"]
    state["offers"].remove(offer)
    return True, f"Offre annulée : {offer['qty']} tokens restitués."


def buy(state, buyer, offer_id, qty):
    offer = next((o for o in state["offers"] if o["id"] == offer_id), None)
    acc = state["accounts"].get(buyer)
    qty = int(qty)
    if offer is None or acc is None:
        return False, "Offre introuvable."
    if offer["seller"] == buyer:
        return False, "Vous ne pouvez pas acheter votre propre offre."
    if acc["province"] != offer["province"]:
        return False, "Les échanges sont limités à une même province."
    if qty <= 0 or qty > offer["qty"]:
        return False, f"Quantité invalide (maximum {offer['qty']})."
    if offer["price"] > state["rules"]["prix_plafond"]:
        return False, "Cette offre dépasse le plafond de prix actuel fixé par l'administration."
    offer["qty"] -= qty
    if offer["qty"] == 0:
        state["offers"].remove(offer)
    acc["balance"] += qty
    _tx(state, type="trade", seller=offer["seller"], buyer=buyer, qty=qty,
        price=offer["price"], province=offer["province"], note="")
    return True, f"Achat de {qty} tokens à {offer['price']:.2f} MAD, soit {qty * offer['price']:.0f} MAD."


def update_rules(state, prix_ref, prix_plafond):
    if prix_ref <= 0 or prix_plafond < prix_ref:
        return False, "Le plafond doit être supérieur ou égal au prix de référence."
    state["rules"]["prix_ref"] = float(prix_ref)
    state["rules"]["prix_plafond"] = float(prix_plafond)
    return True, "Règles mises à jour."