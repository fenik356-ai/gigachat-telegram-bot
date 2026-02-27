import json
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

MEMORY_FILE = Path(__file__).resolve().parent / "user_memory.json"
APP_TIMEZONE = ZoneInfo("America/Chicago")
_LOCK = Lock()

MAX_SAVED_REPLIES = 15
MAX_TEMPLATES = 15


def _today_str() -> str:
    return datetime.now(APP_TIMEZONE).date().isoformat()


def _ensure_file():
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text("{}", encoding="utf-8")


def _load_all() -> dict:
    _ensure_file()

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


def _save_all(data: dict):
    temp_path = MEMORY_FILE.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(MEMORY_FILE)


def _default_stats() -> dict:
    return {
        "activity_dates": [],
        "generation_count": 0,
        "analysis_count": 0,
        "dialog_count": 0,
        "saved_count": 0,
        "coach_view_count": 0,
        "events_by_date": {},
    }


def _user_bucket(data: dict, user_id: int) -> dict:
    key = str(user_id)

    if key not in data or not isinstance(data[key], dict):
        data[key] = {}

    bucket = data[key]

    if "preset" not in bucket:
        bucket["preset"] = None

    if "saved_replies" not in bucket or not isinstance(bucket["saved_replies"], list):
        bucket["saved_replies"] = []

    if "templates" not in bucket or not isinstance(bucket["templates"], list):
        bucket["templates"] = []

    if "people" not in bucket or not isinstance(bucket["people"], dict):
        bucket["people"] = {}

    if "stats" not in bucket or not isinstance(bucket["stats"], dict):
        bucket["stats"] = _default_stats()

    stats = bucket["stats"]

    for k, v in _default_stats().items():
        if k not in stats:
            stats[k] = v

    if not isinstance(stats["activity_dates"], list):
        stats["activity_dates"] = []

    if not isinstance(stats["events_by_date"], dict):
        stats["events_by_date"] = {}

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

    return bucket


def _normalize_text(value: str, limit: int = 1200) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


def _dedupe_keep_first(items: list[str], max_items: int) -> list[str]:
    result = []
    seen = set()

    for item in items:
        text = _normalize_text(item)
        if not text:
            continue

        key = text.lower()
        if key in seen:
            continue

        seen.add(key)
        result.append(text)

        if len(result) >= max_items:
            break

    return result


def _calculate_streaks(activity_dates: list[str]) -> tuple[int, int]:
    parsed = []

    for item in activity_dates:
        try:
            parsed.append(date.fromisoformat(str(item)))
        except ValueError:
            continue

    if not parsed:
        return 0, 0

    unique_dates = sorted(set(parsed))
    best_streak = 1
    run = 1

    for index in range(1, len(unique_dates)):
        if unique_dates[index] == unique_dates[index - 1] + timedelta(days=1):
            run += 1
            best_streak = max(best_streak, run)
        else:
            run = 1

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


def _build_achievements(stats: dict) -> list[str]:
    achievements = []

    if stats["total_active_days"] >= 1:
        achievements.append("Первый день активности")

    if stats["generation_count"] >= 10:
        achievements.append("10 генераций")

    if stats["analysis_count"] + stats["dialog_count"] >= 5:
        achievements.append("5 разборов")

    if stats["saved_replies_count"] >= 3:
        achievements.append("Коллекционер ответов")

    if stats["current_streak"] >= 3 or stats["best_streak"] >= 3:
        achievements.append("Серия 3 дня")

    if stats["best_streak"] >= 7:
        achievements.append("Серия 7 дней")

    return achievements


def get_user_preset(user_id: int):
    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)
        return bucket.get("preset")


def save_user_preset(user_id: int, preset: dict):
    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)

        bucket["preset"] = {
            "tone": preset.get("tone"),
            "goal": preset.get("goal"),
            "variants_count": preset.get("variants_count"),
            "scenario": preset.get("scenario"),
        }

        _save_all(data)


def get_saved_replies(user_id: int) -> list[str]:
    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)
        bucket["saved_replies"] = _dedupe_keep_first(bucket["saved_replies"], MAX_SAVED_REPLIES)
        _save_all(data)
        return list(bucket["saved_replies"])


def save_reply_to_memory(user_id: int, reply_text: str) -> int:
    clean_text = _normalize_text(reply_text)

    if not clean_text:
        return 0

    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)

        current = [clean_text] + bucket["saved_replies"]
        bucket["saved_replies"] = _dedupe_keep_first(current, MAX_SAVED_REPLIES)

        _save_all(data)
        return len(bucket["saved_replies"])


def get_saved_templates(user_id: int) -> list[str]:
    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)
        bucket["templates"] = _dedupe_keep_first(bucket["templates"], MAX_TEMPLATES)
        _save_all(data)
        return list(bucket["templates"])


def save_template_to_memory(user_id: int, template_text: str) -> int:
    clean_text = _normalize_text(template_text)

    if not clean_text:
        return 0

    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)

        current = [clean_text] + bucket["templates"]
        bucket["templates"] = _dedupe_keep_first(current, MAX_TEMPLATES)

        _save_all(data)
        return len(bucket["templates"])


def get_people_notes(user_id: int) -> list[dict]:
    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)

        result = []
        for _, item in bucket["people"].items():
            if not isinstance(item, dict):
                continue

            name = _normalize_text(str(item.get("name", "")), 80)
            note = _normalize_text(str(item.get("note", "")), 300)

            if not name or not note:
                continue

            result.append({"name": name, "note": note})

        result.sort(key=lambda x: x["name"].lower())
        return result


def get_person_note(user_id: int, person_name: str) -> str:
    key = _normalize_text(person_name, 80).lower()

    if not key:
        return ""

    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)
        item = bucket["people"].get(key)

        if not isinstance(item, dict):
            return ""

        return _normalize_text(str(item.get("note", "")), 300)


def upsert_person_note(user_id: int, raw_entry: str) -> tuple[bool, str]:
    text = (raw_entry or "").strip()

    if ":" not in text:
        return False, ""

    name_part, note_part = text.split(":", 1)
    name = _normalize_text(name_part, 80)
    note = _normalize_text(note_part, 300)

    if not name or not note:
        return False, ""

    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)

        bucket["people"][name.lower()] = {
            "name": name,
            "note": note,
        }

        _save_all(data)

    return True, name


def register_user_event(user_id: int, event_type: str = "generation") -> dict:
    counter_map = {
        "generation": "generation_count",
        "analysis": "analysis_count",
        "dialog": "dialog_count",
        "save": "saved_count",
        "coach": "coach_view_count",
    }

    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)
        stats = bucket["stats"]

        today = _today_str()

        activity_dates = [str(x) for x in stats["activity_dates"] if str(x).strip()]
        if today not in activity_dates:
            activity_dates.append(today)

        stats["activity_dates"] = sorted(set(activity_dates))

        counter_key = counter_map.get(event_type)
        if counter_key:
            stats[counter_key] = int(stats.get(counter_key, 0)) + 1

        if today not in stats["events_by_date"] or not isinstance(stats["events_by_date"][today], dict):
            stats["events_by_date"][today] = {}

        stats["events_by_date"][today][event_type] = int(
            stats["events_by_date"][today].get(event_type, 0)
        ) + 1

        _save_all(data)

    return get_user_engagement_stats(user_id)


def get_user_engagement_stats(user_id: int) -> dict:
    with _LOCK:
        data = _load_all()
        bucket = _user_bucket(data, user_id)
        stats = bucket["stats"]

        current_streak, best_streak = _calculate_streaks(stats["activity_dates"])

        today = datetime.now(APP_TIMEZONE).date()
        week_dates = [(today - timedelta(days=i)).isoformat() for i in range(7)]

        week = {
            "generation": 0,
            "analysis": 0,
            "dialog": 0,
            "save": 0,
            "coach": 0,
            "active_days": 0,
        }

        for day_key in week_dates:
            if day_key in stats["events_by_date"]:
                week["active_days"] += 1
                day_bucket = stats["events_by_date"][day_key]

                for metric in ["generation", "analysis", "dialog", "save", "coach"]:
                    week[metric] += int(day_bucket.get(metric, 0))

        result = {
            "total_active_days": len(stats["activity_dates"]),
            "current_streak": current_streak,
            "best_streak": best_streak,
            "generation_count": int(stats["generation_count"]),
            "analysis_count": int(stats["analysis_count"]),
            "dialog_count": int(stats["dialog_count"]),
            "saved_count": int(stats["saved_count"]),
            "coach_view_count": int(stats["coach_view_count"]),
            "saved_replies_count": len(_dedupe_keep_first(bucket["saved_replies"], MAX_SAVED_REPLIES)),
            "templates_count": len(_dedupe_keep_first(bucket["templates"], MAX_TEMPLATES)),
            "week": week,
        }

        result["achievements"] = _build_achievements(result)
        return result