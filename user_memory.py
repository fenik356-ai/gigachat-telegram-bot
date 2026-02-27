import json
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

MEMORY_FILE = Path(__file__).resolve().parent / "user_memory.json"
_LOCK = Lock()
APP_TIMEZONE = ZoneInfo("America/Chicago")

MAX_SAVED_REPLIES = 10
MAX_REPLY_LENGTH = 1200
MAX_ACTIVITY_DATES = 120


def _ensure_file_exists():
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text("{}", encoding="utf-8")


def _backup_corrupted_file():
    if not MEMORY_FILE.exists():
        return

    timestamp = datetime.now(APP_TIMEZONE).strftime("%Y%m%d_%H%M%S")
    backup_path = MEMORY_FILE.with_name(f"user_memory.corrupted_{timestamp}.json")

    try:
        MEMORY_FILE.replace(backup_path)
    except Exception:
        pass


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

    clean_dates = sorted(set(clean_dates))
    return clean_dates[-MAX_ACTIVITY_DATES:]


def _sanitize_saved_replies(raw_replies) -> list[str]:
    if not isinstance(raw_replies, list):
        return []

    cleaned = []
    seen = set()

    for item in raw_replies:
        text = " ".join(str(item).split()).strip()

        if not text:
            continue

        if len(text) > MAX_REPLY_LENGTH:
            text = text[:MAX_REPLY_LENGTH] + "..."

        if text in seen:
            continue

        seen.add(text)
        cleaned.append(text)

        if len(cleaned) >= MAX_SAVED_REPLIES:
            break

    return cleaned


def _sanitize_preset(raw_preset):
    if not isinstance(raw_preset, dict):
        return None

    return {
        "tone": raw_preset.get("tone"),
        "goal": raw_preset.get("goal"),
        "variants_count": raw_preset.get("variants_count"),
        "scenario": raw_preset.get("scenario"),
    }


def _sanitize_stats(raw_stats) -> dict:
    if not isinstance(raw_stats, dict):
        raw_stats = {}

    stats = {
        "activity_dates": _normalize_activity_dates(raw_stats.get("activity_dates", [])),
        "generation_count": 0,
        "analysis_count": 0,
        "dialog_count": 0,
        "saved_count": 0,
        "coach_view_count": 0,
    }

    for key in [
        "generation_count",
        "analysis_count",
        "dialog_count",
        "saved_count",
        "coach_view_count",
    ]:
        try:
            value = int(raw_stats.get(key, 0))
            stats[key] = max(0, value)
        except (TypeError, ValueError):
            stats[key] = 0

    return stats


def _default_user_bucket() -> dict:
    return {
        "preset": None,
        "saved_replies": [],
        "stats": _sanitize_stats({}),
    }


def _sanitize_user_bucket(raw_bucket) -> dict:
    if not isinstance(raw_bucket, dict):
        return _default_user_bucket()

    return {
        "preset": _sanitize_preset(raw_bucket.get("preset")),
        "saved_replies": _sanitize_saved_replies(raw_bucket.get("saved_replies", [])),
        "stats": _sanitize_stats(raw_bucket.get("stats", {})),
    }


def _sanitize_memory_data(raw_data) -> dict:
    if not isinstance(raw_data, dict):
        return {}

    clean_data = {}

    for raw_user_id, raw_bucket in raw_data.items():
        user_id = str(raw_user_id).strip()

        if not user_id:
            continue

        clean_data[user_id] = _sanitize_user_bucket(raw_bucket)

    return clean_data


def _atomic_write_json(data: dict):
    temp_path = MEMORY_FILE.with_suffix(".tmp")

    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(MEMORY_FILE)


def _load_memory() -> dict:
    _ensure_file_exists()

    try:
        raw = MEMORY_FILE.read_text(encoding="utf-8").strip()

        if not raw:
            return {}

        parsed = json.loads(raw)
        return _sanitize_memory_data(parsed)

    except json.JSONDecodeError:
        _backup_corrupted_file()
        _ensure_file_exists()
        return {}

    except Exception:
        return {}


def _save_memory(data: dict):
    safe_data = _sanitize_memory_data(data)
    _atomic_write_json(safe_data)


def _today_str() -> str:
    return datetime.now(APP_TIMEZONE).date().isoformat()


def _get_user_bucket(data: dict, user_id: int) -> dict:
    key = str(user_id)

    if key not in data or not isinstance(data[key], dict):
        data[key] = _default_user_bucket()
    else:
        data[key] = _sanitize_user_bucket(data[key])

    return data[key]


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
    bucket = _sanitize_user_bucket(bucket)
    stats = bucket["stats"]
    saved_replies = bucket["saved_replies"]

    current_streak, best_streak = _calculate_streaks(stats["activity_dates"])

    result = {
        "total_active_days": len(stats["activity_dates"]),
        "current_streak": current_streak,
        "best_streak": best_streak,
        "generation_count": stats["generation_count"],
        "analysis_count": stats["analysis_count"],
        "dialog_count": stats["dialog_count"],
        "saved_count": stats["saved_count"],
        "coach_view_count": stats["coach_view_count"],
        "saved_replies_count": len(saved_replies),
    }

    result["achievements"] = _build_achievements(result, len(saved_replies))
    return result


def get_user_preset(user_id: int):
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        _save_memory(data)
        return bucket.get("preset")


def save_user_preset(user_id: int, preset: dict):
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        bucket["preset"] = _sanitize_preset(preset)
        _save_memory(data)


def get_saved_replies(user_id: int) -> list[str]:
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        _save_memory(data)
        return list(bucket["saved_replies"])


def save_reply_to_memory(user_id: int, reply_text: str) -> int:
    clean_text = " ".join((reply_text or "").split()).strip()

    if not clean_text:
        return 0

    if len(clean_text) > MAX_REPLY_LENGTH:
        clean_text = clean_text[:MAX_REPLY_LENGTH] + "..."

    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)

        replies = [item for item in bucket["saved_replies"] if item != clean_text]
        replies.insert(0, clean_text)
        bucket["saved_replies"] = _sanitize_saved_replies(replies)

        _save_memory(data)
        return len(bucket["saved_replies"])


def register_user_event(user_id: int, event_type: str = "generation") -> dict:
    with _LOCK:
        data = _load_memory()
        bucket = _get_user_bucket(data, user_id)
        stats = bucket["stats"]

        today = _today_str()

        activity_dates = list(stats["activity_dates"])
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
            stats[counter_key] = max(0, int(stats.get(counter_key, 0)) + 1)

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