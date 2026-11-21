import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FARMS_FILE = DATA_DIR / "farms.json"


def _load() -> dict:
    if FARMS_FILE.exists():
        return json.loads(FARMS_FILE.read_text(encoding="utf-8"))
    return {}


def get_farm(username: str):
    return _load().get(username)


def save_farm(username: str, config: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    data = _load()
    data[username] = config
    FARMS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def all_farms() -> dict:
    """Utilisé plus tard par le dashboard administrateur."""
    return _load()