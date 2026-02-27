import json
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

MEMORY_FILE = Path(__file__).resolve().parent / "user_memory.json"
_LOCK = Lock()
APP_TIMEZONE = ZoneInfo("America/Chicago")


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


def _today_str() -> str:
    return datetime.now(APP_TIMEZONE).date().isoformat()


def _get_user_bucket(data: dict, user_id: int) -> dict:
    key = str(user_id)

    if key not in data or not isinstance(data[key], dict):
        data[key] = {
            "preset": None,
            "saved_replies": [],
            "stats": {},
        }

    if "preset" not in data[key]:
        data[key]["preset"] = None

    if "saved_replies" not in data[key] or not isinstance(data[key]["saved_replies"], list):
        data[key]["saved_replies"] = []

    if "stats" not in data[key] or not isinstance(data[key]["stats"], dict):
        data[key]["stats"] = {}

    return data[key]


def _get_stats_bucket(bucket: dict) -> dict:
    stats = bucket.get("stats")

    if not isinstance(stats, dict):
        stats = {}
        bucket["stats"] = stats

    defaults = {
        "activity_dates": [],
        "generation_count": 0,
        "analysis_count": 0,
        "dialog_count": 0,
        "saved_count": 0,
        "coach_view_count": 0,
    }

    for key, default_value in defaults.items():
        if key not in stats:
            stats[key] = default_value

    if not isinstance(stats["activity_dates"], list):
        stats["activity_dates"] = []

    for int_key in [
        "generation_count",
        "analysis_count",
        "dialog_count",
        "saved_count",
        "coach_view_count",
    ]:
        try:
            stats[int_key] = int(stats.get(int_key, 0))
        except (TypeError, ValueError):
            stats[int_key] = 0

    return stats


def _normalize_activity_dates(raw_dates: list) -> list[str]:
    clean_dates = []

    for item in raw_dates:
        value = str(item).strip()
        if not value:
            continue
        try:
            date.fromisoformat(value)
            clean_dates.append(value)
        except ValueError:
            continue

    return sorted(set(clean_dates))


def _calculate_streaks(activity_dates: list[str]) -> tuple[int, int]:
    if not activity_dates:
        return 0, 0

    date_objects = []
    for item in activity_dates:
        try:
            date_objects.append(date.fromisoformat(item))
        except ValueError:
            continue

    if not date_objects:
        return 0, 0

    unique_dates = sorted(set(date_objects))
    best_streak = 1
    current_run = 1

    for index in range(1, len(unique_dates)):
        if unique_dates[index] == unique_dates[index - 1] + timedelta(days=1):
            current_run += 1
            if current_run > best_streak:
                best_streak = current_run
        else:
            current_run = 1

    today = datetime.now(APP_TIMEZONE).date()
    active_set = set(unique_dates)

    if today not in active_set:
        current_streak = 0
    else:
        current_streak = 1
        cursor = today - timedelta(days=1)

        while cursor in active_set:
            current_streak += 1
            cursor -= timedelta(days=1)

    return current_streak, best_streak


def _build_achievements(stats: dict, saved_replies_count: int) -> list[str]:
    achievements = []

    total_active_days = stats["total_active_days"]
    current_streak = stats["current_streak"]
    best_streak = stats["best_streak"]
    generation_count = stats["generation_count"]
    analysis_total = stats["analysis_count"] + stats["dialog_count"]
    saved_total = max(stats["saved_count"], saved_replies_count)

    if total_active_days >= 1:
        achievements.append("Первый день активности")

    if generation_count >= 10:
        achievements.append("10 генераций")

    if analysis_total >= 5:
        achievements.append("5 разборов")

    if saved_total >= 3:
        achievements.append("Коллекционер ответов")

    if current_streak >= 3 or best_streak >= 3:
        achievements.append("Серия 3 дня")

    if best_streak >= 7:
        achievements.append("Серия 7 дней")

    return achievements


def _build_engagement_stats(bucket: dict) -> dict:
    stats = _get_stats_bucket(bucket)
    activity_dates = _normalize_activity_dates(stats.get("activity_dates", []))
    stats["activity_dates"] = activity_dates

    current_streak, best_streak = _calculate_streaks(activity_dates)
    saved_replies = [str(item).strip() for item in bucket.get("saved_replies", []) if str(item).strip()]

    result = {
        "total_active_days": len(activity_dates),
        "current_streak": current_streak,
        "best_streak": best_streak,
        "generation_count": int(stats.get("generation_count", 0)),
        "analysis_count": int(stats.get("analysis_count", 0)),
        "dialog_count": int(stats.get("dialog_count", 0)),
        "saved_count": int(stats.get("saved_count", 0)),
        "coach_view_count": int(stats.get("coach_view_count", 0)),
        "saved_replies_count": len(saved_replies),
    }

    result["achievements"] = _build_achievements(result, len(saved_replies))
    return result


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


def register_user_event(user_id: int, event_type: str = "generation") -> dict:
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        stats = _get_stats_bucket(bucket)

        today = _today_str()
        activity_dates = _normalize_activity_dates(stats.get("activity_dates", []))

        if today not in activity_dates:
            activity_dates.append(today)

        stats["activity_dates"] = _normalize_activity_dates(activity_dates)

        counter_map = {
            "generation": "generation_count",
            "analysis": "analysis_count",
            "dialog": "dialog_count",
            "save": "saved_count",
            "coach": "coach_view_count",
        }

        counter_key = counter_map.get(event_type)
        if counter_key:
            stats[counter_key] = int(stats.get(counter_key, 0)) + 1

        result = _build_engagement_stats(bucket)
        _save_memory(data)
        return result


def get_user_engagement_stats(user_id: int) -> dict:
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        result = _build_engagement_stats(bucket)
        _save_memory(data)
        return result