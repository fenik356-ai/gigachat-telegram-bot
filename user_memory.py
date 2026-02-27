import json
from pathlib import Path
from threading import Lock

MEMORY_FILE = Path(__file__).resolve().parent / "user_memory.json"
_LOCK = Lock()

DEFAULT_USER_DATA = {
    "preset": None,
    "saved_replies": [],
}


def _ensure_file_exists():
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text("{}", encoding="utf-8")


def _load_memory() -> dict:
    _ensure_file_exists()

    try:
        raw = MEMORY_FILE.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _save_memory(data: dict):
    MEMORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_user_bucket(data: dict, user_id: int) -> dict:
    key = str(user_id)

    if key not in data or not isinstance(data[key], dict):
        data[key] = {
            "preset": None,
            "saved_replies": [],
        }

    if "preset" not in data[key]:
        data[key]["preset"] = None

    if "saved_replies" not in data[key] or not isinstance(data[key]["saved_replies"], list):
        data[key]["saved_replies"] = []

    return data[key]


def get_user_preset(user_id: int):
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        return bucket.get("preset")


def save_user_preset(user_id: int, preset: dict):
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        bucket["preset"] = {
            "tone": preset.get("tone"),
            "goal": preset.get("goal"),
            "variants_count": preset.get("variants_count"),
            "scenario": preset.get("scenario"),
        }
        _save_memory(data)


def get_saved_replies(user_id: int) -> list[str]:
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        replies = bucket.get("saved_replies", [])
        clean_replies = [str(item).strip() for item in replies if str(item).strip()]
        return clean_replies


def save_reply_to_memory(user_id: int, reply_text: str) -> int:
    clean_text = " ".join((reply_text or "").split()).strip()

    if not clean_text:
        return 0

    if len(clean_text) > 1200:
        clean_text = clean_text[:1200] + "..."

    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        replies = bucket.get("saved_replies", [])

        replies = [item for item in replies if item != clean_text]
        replies.insert(0, clean_text)

        replies = replies[:10]
        bucket["saved_replies"] = replies

        _save_memory(data)
        return len(replies)