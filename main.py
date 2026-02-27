import asyncio
import os
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

from gigachat_api import (
    analyze_dialog_v2,
    analyze_single_message_v2,
    build_message_from_brief,
    compare_reply_variants,
    generate_baseline_reply,
    generate_reply_options_v2,
)
from module1_reply_presets import (
    DEFAULT_TONE,
    GOAL_OPTIONS,
    TONE_OPTIONS,
    get_default_module1_state,
    get_goal_label,
    get_tone_label,
    normalize_variants_count,
)
from scenario_presets import (
    DEFAULT_SCENARIO_KEY,
    SCENARIO_OPTIONS,
    get_scenario_defaults,
    get_scenario_instruction,
    get_scenario_label,
    get_scenario_starter_hint,
)
from user_memory import (
    get_people_notes,
    get_person_note,
    get_saved_replies,
    get_saved_templates,
    get_user_engagement_stats,
    get_user_preset,
    register_user_event,
    save_reply_to_memory,
    save_template_to_memory,
    save_user_preset,
    upsert_person_note,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("В файле .env не найден BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_dialogues = {}
user_module1_settings = {}
user_analysis_modes = {}
user_dialog_analysis_modes = {}
user_scenarios = {}
user_flow_modes = {}

result_message_payloads = {}

MAX_HISTORY_LINES = 6
MAX_SAVED_RESULTS = 200

FLOW_QUICK = "quick"
FLOW_ANALYZE_MESSAGE = "analyze_message"
FLOW_ANALYZE_DIALOG = "analyze_dialog"
FLOW_BUILDER = "builder"
FLOW_PERSON_NOTE = "person_note"

ANALYSIS_MODE_LABELS = {
    "general": "Полный",
    "meaning": "Смысл",
    "risk": "Риск",
    "before_send": "Перед отправкой",
    "reaction": "Реакция",
}

DIALOG_ANALYSIS_MODE_LABELS = {
    "general": "Полный",
    "dynamics": "Динамика",
    "interest": "Интерес",
    "mistakes": "Ошибки",
    "next_step": "Следующий шаг",
}

SCENARIO_GROUPS = {
    "personal": {
        "label": "Личное",
        "items": [
            "dating_intro",
            "relationships",
            "restore_contact",
            "reconcile_chat",
            "first_message",
            "rescue_chat",
        ],
    },
    "business": {
        "label": "Деловое",
        "items": [
            "business",
            "sales",
            "support",
            "close_result",
        ],
    },
    "hard": {
        "label": "Сложные ситуации",
        "items": [
            "soft_decline",
            "boundaries",
            "hard_talk",
            "difficult_person",
        ],
    },
}


def get_user_module1_state(user_id: int) -> dict:
    if user_id not in user_module1_settings:
        user_module1_settings[user_id] = get_default_module1_state()
    return user_module1_settings[user_id]


def get_user_analysis_mode(user_id: int) -> str:
    if user_id not in user_analysis_modes:
        user_analysis_modes[user_id] = "general"
    return user_analysis_modes[user_id]


def get_user_dialog_analysis_mode(user_id: int) -> str:
    if user_id not in user_dialog_analysis_modes:
        user_dialog_analysis_modes[user_id] = "general"
    return user_dialog_analysis_modes[user_id]


def get_user_scenario(user_id: int) -> str:
    if user_id not in user_scenarios:
        user_scenarios[user_id] = DEFAULT_SCENARIO_KEY
    return user_scenarios[user_id]


def get_user_flow_mode(user_id: int) -> str:
    if user_id not in user_flow_modes:
        user_flow_modes[user_id] = FLOW_QUICK
    return user_flow_modes[user_id]


def set_user_flow_mode(user_id: int, flow_mode: str):
    user_flow_modes[user_id] = flow_mode


def apply_tone_to_state(state: dict, tone_value: str):
    if tone_value == "neutral":
        state["tone"] = DEFAULT_TONE
        return

    if tone_value in TONE_OPTIONS:
        state["tone"] = tone_value


def apply_saved_preset_if_exists(user_id: int) -> bool:
    preset = get_user_preset(user_id)

    if not preset or not isinstance(preset, dict):
        return False

    state = get_user_module1_state(user_id)

    tone = preset.get("tone")
    goal = preset.get("goal")
    variants_count = preset.get("variants_count")
    scenario = preset.get("scenario")

    apply_tone_to_state(state, tone)

    if goal in GOAL_OPTIONS:
        state["goal"] = goal

    state["variants_count"] = normalize_variants_count(variants_count)

    if scenario in SCENARIO_OPTIONS:
        user_scenarios[user_id] = scenario
    else:
        user_scenarios[user_id] = DEFAULT_SCENARIO_KEY

    return True


def add_to_history(user_id: int, speaker: str, text: str):
    clean_text = " ".join((text or "").split()).strip()

    if not clean_text:
        return

    if len(clean_text) > 500:
        clean_text = clean_text[:500] + "..."

    history = user_dialogues.get(user_id, [])
    history.append(f"{speaker}: {clean_text}")
    user_dialogues[user_id] = history[-MAX_HISTORY_LINES:]


def get_dialogue_context(user_id: int) -> str:
    history = user_dialogues.get(user_id, [])
    return "\n".join(history)


def make_result_key(chat_id: int, message_id: int):
    return (chat_id, message_id)


def get_result_payload(chat_id: int, message_id: int):
    return result_message_payloads.get(make_result_key(chat_id, message_id))


def save_result_payload(
    chat_id: int,
    message_id: int,
    user_id: int,
    source_text: str,
    effective_source_text: str,
    dialogue_context: str,
    tone_key: str,
    goal_key: str,
    scenario_key: str,
    variants_count: int,
    result: dict,
):
    result_message_payloads[make_result_key(chat_id, message_id)] = {
        "user_id": user_id,
        "source_text": source_text,
        "effective_source_text": effective_source_text,
        "dialogue_context": dialogue_context,
        "tone_key": tone_key,
        "goal_key": goal_key,
        "scenario_key": scenario_key,
        "variants_count": variants_count,
        "variants": result["variants"],
        "best_index": result["best_index"],
        "best_reason": result["best_reason"],
        "best_variant_text": result["best_variant_text"],
    }

    if len(result_message_payloads) > MAX_SAVED_RESULTS:
        oldest_key = next(iter(result_message_payloads))
        result_message_payloads.pop(oldest_key, None)


def extract_command_payload_or_reply_text(message: Message) -> str:
    raw_text = message.text or ""
    parts = raw_text.split(maxsplit=1)

    if len(parts) > 1 and parts[1].strip():
        return parts[1].strip()

    reply_to = message.reply_to_message
    if reply_to and reply_to.text and reply_to.text.strip():
        return reply_to.text.strip()

    return ""


def extract_person_context(user_id: int, raw_text: str) -> tuple[str, Optional[str], Optional[str]]:
    text = (raw_text or "").strip()

    if not text.startswith("@"):
        return text, None, None

    if ":" not in text[:80]:
        return text, None, None

    head, body = text[1:].split(":", 1)
    person_name = " ".join(head.split()).strip()
    clean_body = body.strip()

    if not person_name or not clean_body:
        return text, None, None

    note = get_person_note(user_id, person_name)

    if not note:
        return clean_body, None, None

    return clean_body, person_name, note


def build_effective_scenario_text(raw_text: str, scenario_key: str) -> str:
    if scenario_key not in SCENARIO_OPTIONS:
        scenario_key = DEFAULT_SCENARIO_KEY

    if scenario_key == DEFAULT_SCENARIO_KEY:
        return raw_text

    scenario_instruction = get_scenario_instruction(scenario_key)

    return (
        "Это задача для генерации ответа в конкретном сценарии.\n"
        f"Сценарий: {scenario_instruction}.\n"
        "Нужно предложить варианты ответа именно для такой ситуации.\n"
        f"Исходное сообщение / ситуация:\n{raw_text}"
    )


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="⚡ Быстрый ответ"),
                KeyboardButton(text="🔍 Разбор"),
            ],
            [
                KeyboardButton(text="🎭 Сценарии"),
                KeyboardButton(text="💾 Сохранённые"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="🧠 Коуч"),
            ],
            [
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери раздел или просто отправь текст…",
    )


def build_quick_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Ввести текст",
                    callback_data="flow:quick",
                ),
                InlineKeyboardButton(
                    text="🧩 Конструктор",
                    callback_data="flow:builder",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Настроить",
                    callback_data="hub:settings",
                ),
                InlineKeyboardButton(
                    text="🎭 Сценарий",
                    callback_data="set:scenarios",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                )
            ],
        ]
    )


def build_analyze_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Разобрать сообщение",
                    callback_data="flow:an_message",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Разобрать переписку",
                    callback_data="flow:an_dialog",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Режим сообщения",
                    callback_data="open:analysis_modes",
                ),
                InlineKeyboardButton(
                    text="Режим переписки",
                    callback_data="open:dialog_modes",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                )
            ],
        ]
    )


def build_memory_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Ответы",
                    callback_data="memory:saved",
                ),
                InlineKeyboardButton(
                    text="🗂 Шаблоны",
                    callback_data="memory:templates",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👤 Люди",
                    callback_data="memory:people",
                ),
                InlineKeyboardButton(
                    text="🧠 Мой пресет",
                    callback_data="memory:my_preset",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Сохранить пресет",
                    callback_data="memory:save_preset",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                )
            ],
        ]
    )


def build_people_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить / обновить",
                    callback_data="memory:add_person",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К сохранённым",
                    callback_data="hub:memory",
                ),
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                ),
            ],
        ]
    )


def build_templates_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ К сохранённым",
                    callback_data="hub:memory",
                ),
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                ),
            ],
        ]
    )


def build_settings_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Тон",
                    callback_data="set:tones",
                ),
                InlineKeyboardButton(
                    text="Цель",
                    callback_data="set:goals",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Сценарий",
                    callback_data="set:scenarios",
                ),
                InlineKeyboardButton(
                    text="Варианты",
                    callback_data="set:variants",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧹 Сбросить контекст",
                    callback_data="settings:reset_history",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                )
            ],
        ]
    )


def build_coach_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 На сегодня",
                    callback_data="coach:today",
                ),
                InlineKeyboardButton(
                    text="📈 Прогресс",
                    callback_data="coach:progress",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📅 За неделю",
                    callback_data="coach:week",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                )
            ],
        ]
    )


def build_tone_keyboard(user_id: int) -> InlineKeyboardMarkup:
    state = get_user_module1_state(user_id)
    current_tone = state["tone"]

    def tone_text(key: str, label: str) -> str:
        return f"✅ {label}" if current_tone == key else label

    normal = "✅ Обычный" if current_tone == DEFAULT_TONE else "Обычный"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=normal,
                    callback_data="m1_tone:neutral",
                )
            ],
            [
                InlineKeyboardButton(
                    text=tone_text("shorter", "Короче"),
                    callback_data="m1_tone:shorter",
                ),
                InlineKeyboardButton(
                    text=tone_text("softer", "Мягче"),
                    callback_data="m1_tone:softer",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=tone_text("bolder", "Увереннее"),
                    callback_data="m1_tone:bolder",
                ),
                InlineKeyboardButton(
                    text=tone_text("warmer", "Теплее"),
                    callback_data="m1_tone:warmer",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=tone_text("colder", "Холоднее"),
                    callback_data="m1_tone:colder",
                ),
                InlineKeyboardButton(
                    text=tone_text("funnier", "Смешнее"),
                    callback_data="m1_tone:funnier",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=tone_text("smarter", "Умнее"),
                    callback_data="m1_tone:smarter",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К настройкам",
                    callback_data="hub:settings",
                )
            ],
        ]
    )


def build_goal_keyboard(user_id: int) -> InlineKeyboardMarkup:
    state = get_user_module1_state(user_id)
    current_goal = state["goal"]

    def goal_text(key: str, label: str) -> str:
        return f"✅ {label}" if current_goal == key else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=goal_text("get_reply", "Получить ответ"),
                    callback_data="m1_goal:get_reply",
                ),
                InlineKeyboardButton(
                    text=goal_text("keep_interest", "Удержать интерес"),
                    callback_data="m1_goal:keep_interest",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=goal_text("book_meeting", "Закрыть на встречу"),
                    callback_data="m1_goal:book_meeting",
                ),
                InlineKeyboardButton(
                    text=goal_text("decline", "Отказать"),
                    callback_data="m1_goal:decline",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=goal_text("reconcile", "Помириться"),
                    callback_data="m1_goal:reconcile",
                ),
                InlineKeyboardButton(
                    text=goal_text("sell", "Продать"),
                    callback_data="m1_goal:sell",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К настройкам",
                    callback_data="hub:settings",
                )
            ],
        ]
    )


def build_variants_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current = get_user_module1_state(user_id)["variants_count"]

    def item(count: int) -> str:
        return f"✅ {count}" if current == count else str(count)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=item(3), callback_data="m1_variants:3"),
                InlineKeyboardButton(text=item(4), callback_data="m1_variants:4"),
                InlineKeyboardButton(text=item(5), callback_data="m1_variants:5"),
            ],
            [
                InlineKeyboardButton(text=item(6), callback_data="m1_variants:6"),
                InlineKeyboardButton(text=item(7), callback_data="m1_variants:7"),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К настройкам",
                    callback_data="hub:settings",
                )
            ],
        ]
    )


def build_scenario_group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🙂 Обычный",
                    callback_data="sc_mode:neutral",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👋 Личное",
                    callback_data="sc_group:personal",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💼 Деловое",
                    callback_data="sc_group:business",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛡 Сложные ситуации",
                    callback_data="sc_group:hard",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="hub:settings",
                ),
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                ),
            ],
        ]
    )


def build_scenario_items_keyboard(group_key: str, user_id: int) -> InlineKeyboardMarkup:
    current_scenario = get_user_scenario(user_id)
    rows = []

    for scenario_key in SCENARIO_GROUPS[group_key]["items"]:
        label = get_scenario_label(scenario_key)
        if current_scenario == scenario_key:
            label = f"✅ {label}"

        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"sc_mode:{scenario_key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Категории",
                callback_data="set:scenarios",
            ),
            InlineKeyboardButton(
                text="🏠 В меню",
                callback_data="nav:main",
            ),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_analysis_mode_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current = get_user_analysis_mode(user_id)

    def item(key: str) -> str:
        label = ANALYSIS_MODE_LABELS[key]
        return f"✅ {label}" if current == key else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=item("general"), callback_data="an_mode:general"),
                InlineKeyboardButton(text=item("meaning"), callback_data="an_mode:meaning"),
            ],
            [
                InlineKeyboardButton(text=item("risk"), callback_data="an_mode:risk"),
                InlineKeyboardButton(text=item("before_send"), callback_data="an_mode:before_send"),
            ],
            [
                InlineKeyboardButton(text=item("reaction"), callback_data="an_mode:reaction"),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К разбору",
                    callback_data="hub:analyze",
                )
            ],
        ]
    )


def build_dialog_mode_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current = get_user_dialog_analysis_mode(user_id)

    def item(key: str) -> str:
        label = DIALOG_ANALYSIS_MODE_LABELS[key]
        return f"✅ {label}" if current == key else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=item("general"), callback_data="dlg_mode:general"),
                InlineKeyboardButton(text=item("dynamics"), callback_data="dlg_mode:dynamics"),
            ],
            [
                InlineKeyboardButton(text=item("interest"), callback_data="dlg_mode:interest"),
                InlineKeyboardButton(text=item("mistakes"), callback_data="dlg_mode:mistakes"),
            ],
            [
                InlineKeyboardButton(text=item("next_step"), callback_data="dlg_mode:next_step"),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К разбору",
                    callback_data="hub:analyze",
                )
            ],
        ]
    )


def build_result_actions_keyboard(variants_count: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Взять лучший",
                callback_data="m1_pick_best",
            ),
            InlineKeyboardButton(
                text="🔁 Ещё варианты",
                callback_data="m1_regen",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⚖️ Сравнить",
                callback_data="m1_compare",
            ),
            InlineKeyboardButton(
                text="🔎 Проверить",
                callback_data="result_tools:open",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⭐ Сохранить",
                callback_data="m1_save_best",
            ),
            InlineKeyboardButton(
                text="🗂 Шаблон",
                callback_data="m1_save_template",
            ),
        ],
    ]

    pick_buttons = [
        InlineKeyboardButton(
            text=str(index),
            callback_data=f"m1_pick:{index}",
        )
        for index in range(1, variants_count + 1)
    ]

    for i in range(0, len(pick_buttons), 4):
        rows.append(pick_buttons[i:i + 4])

    rows.append(
        [
            InlineKeyboardButton(
                text="⚙️ Настроить",
                callback_data="hub:settings",
            ),
            InlineKeyboardButton(
                text="🏠 В меню",
                callback_data="nav:main",
            ),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_result_tools_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Перед отправкой",
                    callback_data="result_tool:before_send",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Детектор риска",
                    callback_data="result_tool:risk",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Прогноз реакции",
                    callback_data="result_tool:reaction",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚡ К ответу",
                    callback_data="hub:quick",
                ),
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                ),
            ],
        ]
    )


def build_status_text(user_id: int) -> str:
    state = get_user_module1_state(user_id)
    tone_key = state["tone"]
    goal_key = state["goal"]
    variants_count = state["variants_count"]
    scenario_key = get_user_scenario(user_id)

    tone_label = "Обычный" if tone_key == DEFAULT_TONE else get_tone_label(tone_key)

    return (
        "Сейчас у тебя так:\n"
        f"• Тон: {tone_label}\n"
        f"• Цель: {get_goal_label(goal_key)}\n"
        f"• Сценарий: {get_scenario_label(scenario_key)}\n"
        f"• Вариантов: {variants_count}"
    )


def build_saved_replies_text(user_id: int) -> str:
    replies = get_saved_replies(user_id)

    if not replies:
        return "Пока пусто.\n\nСохрани сильный ответ — и он появится здесь."

    lines = ["Сохранённые ответы:"]
    for index, item in enumerate(replies, start=1):
        lines.append(f"\n{index}. {item}")

    return "\n".join(lines)


def build_templates_text(user_id: int) -> str:
    templates = get_saved_templates(user_id)

    if not templates:
        return "Шаблонов пока нет.\n\nМожешь сохранить лучший ответ как шаблон."

    lines = ["Твои шаблоны:"]
    for index, item in enumerate(templates, start=1):
        lines.append(f"\n{index}. {item}")

    return "\n".join(lines)


def build_people_text(user_id: int) -> str:
    people = get_people_notes(user_id)

    if not people:
        return (
            "Память о людях пока пустая.\n\n"
            "Добавь заметку в формате:\n"
            "Имя: что важно помнить"
        )

    lines = ["Что бот помнит о людях:"]
    for item in people:
        lines.append(f"\n• {item['name']}: {item['note']}")

    lines.append(
        "\n\nЧтобы использовать это в быстром ответе, напиши так:\n"
        "@Имя: твоя ситуация"
    )

    return "\n".join(lines)


def build_progress_text(user_id: int) -> str:
    stats = get_user_engagement_stats(user_id)

    achievements = ["• Пока без достижений — просто продолжай."]
    if stats["achievements"]:
        achievements = [f"• {item}" for item in stats["achievements"]]

    return (
        "Твой прогресс:\n"
        f"• Активных дней: {stats['total_active_days']}\n"
        f"• Текущая серия: {stats['current_streak']}\n"
        f"• Лучшая серия: {stats['best_streak']}\n"
        f"• Генераций: {stats['generation_count']}\n"
        f"• Разборов сообщений: {stats['analysis_count']}\n"
        f"• Разборов переписки: {stats['dialog_count']}\n"
        f"• Сохранённых ответов: {stats['saved_replies_count']}\n"
        f"• Шаблонов: {stats['templates_count']}\n\n"
        "Достижения:\n"
        + "\n".join(achievements)
    )


def build_week_review_text(user_id: int) -> str:
    stats = get_user_engagement_stats(user_id)
    week = stats["week"]

    return (
        "Срез за последние 7 дней:\n"
        f"• Активных дней: {week['active_days']}\n"
        f"• Генераций: {week['generation']}\n"
        f"• Разборов сообщений: {week['analysis']}\n"
        f"• Разборов переписки: {week['dialog']}\n"
        f"• Сохранений: {week['save']}\n"
        f"• Открытий коуча: {week['coach']}\n\n"
        "Это не семантический разбор переписок за неделю, а честный срез твоего использования."
    )


def build_coach_focus(stats: dict) -> str:
    if stats["generation_count"] < 5:
        return "Сделай 3 генерации на реальных сообщениях и сравни, какой вариант сильнее."
    if stats["saved_replies_count"] < 3:
        return "Сохрани хотя бы 1 сильный ответ — это начнёт собирать твою личную библиотеку."
    if stats["analysis_count"] + stats["dialog_count"] < 5:
        return "Разбери хотя бы одно входящее — так ответы становятся заметно точнее."
    if stats["current_streak"] < 3:
        return "Зайди завтра снова — начни собирать серию."
    return "Пройди сегодня полный цикл: разбор → ответ → проверка → сохранить лучший."


def build_coach_tip(user_id: int) -> str:
    scenario_key = get_user_scenario(user_id)

    tips = {
        "neutral": "Чем короче и яснее ты описываешь ситуацию, тем сильнее итоговый ответ.",
        "dating_intro": "В знакомствах сильнее работают лёгкие фразы, на которые просто ответить.",
        "relationships": "В отношениях лучше меньше обороны и больше ясности.",
        "restore_contact": "После паузы мягкий вход почти всегда лучше длинных оправданий.",
        "reconcile_chat": "Чтобы помириться, важнее снизить напряжение, чем доказать свою правоту.",
        "first_message": "Первое сообщение не должно быть идеальным — оно должно быть простым для ответа.",
        "rescue_chat": "Чтобы оживить чат, лучше вернуть лёгкость, а не дожимать разговор.",
        "business": "В деловой переписке одна мысль и один следующий шаг обычно работают лучше всего.",
        "sales": "В продажах убирай давление — усиливай понятную выгоду.",
        "support": "Сначала снизь напряжение, потом веди к решению.",
        "close_result": "Когда нужен результат, формулируй один конкретный следующий шаг.",
        "soft_decline": "Хороший отказ — короткий, ясный и без лишних оправданий.",
        "boundaries": "Границы звучат сильнее, когда ты спокоен, а не когда ты жёсток.",
        "hard_talk": "В сложном разговоре убери лишние эмоции из формулировки — и ты уже выиграешь.",
        "difficult_person": "Со сложным человеком короткий, предсказуемый и ровный ответ сильнее длинного.",
    }

    return tips.get(scenario_key, tips["neutral"])


def build_coach_today_text(user_id: int) -> str:
    stats = get_user_engagement_stats(user_id)
    saved = get_saved_replies(user_id)
    templates = get_saved_templates(user_id)

    if saved:
        top_answer = saved[0]
    elif templates:
        top_answer = templates[0]
    else:
        top_answer = "Пока нет сохранённого ответа дня. Сохрани сильный ответ — и здесь будет твоя лучшая находка."

    return (
        "AI-коуч на сегодня:\n"
        f"• Текущий сценарий: {get_scenario_label(get_user_scenario(user_id))}\n"
        f"• Серия: {stats['current_streak']}\n"
        f"• Активных дней: {stats['total_active_days']}\n\n"
        f"Фокус:\n• {build_coachFocus(stats)}\n\n"
        f"Мини-обучение:\n• {build_coach_tip(user_id)}\n\n"
        f"Топ-ответ дня:\n• {top_answer}"
    )


def build_coachFocus(stats: dict) -> str:
    return build_coach_focus(stats)


def format_result_text(result: dict) -> str:
    lines = ["Вот что можно отправить:\n"]

    for index, variant in enumerate(result["variants"], start=1):
        lines.append(f"{index}. {variant}")

    lines.append("")
    lines.append(f"Лучший сейчас — №{result['best_index']}")
    lines.append(f"Почему: {result['best_reason']}")

    return "\n".join(lines)


async def show_callback_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
):
    if not callback.message:
        return

    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup)


async def show_start_screen(message: Message):
    await message.answer(
        "Привет.\n"
        "Я помогу понять, что лучше ответить, как это прозвучит и что происходит в диалоге.\n\n"
        "Выбери раздел снизу — или просто пришли текст.",
        reply_markup=build_main_menu(),
    )


async def show_quick_hub_message(message: Message, user_id: int):
    set_user_flow_mode(user_id, FLOW_QUICK)
    await message.answer(
        "⚡ Быстрый ответ\n\n"
        "Пришли сообщение или коротко опиши ситуацию — соберу несколько сильных вариантов.",
        reply_markup=build_quick_hub_keyboard(),
    )


async def show_analyze_hub_message(message: Message):
    await message.answer(
        "🔍 Разбор\n\n"
        "Можно разобрать одно сообщение или целую переписку.\n"
        "Сначала выбери, что именно хочешь посмотреть.",
        reply_markup=build_analyze_hub_keyboard(),
    )


async def show_scenarios_hub_message(message: Message, user_id: int):
    await message.answer(
        "🎭 Сценарии\n\n"
        "Выбери категорию — и я подстрою быстрые ответы под эту задачу.",
        reply_markup=build_scenario_group_keyboard(),
    )
    await message.answer(
        f"{build_status_text(user_id)}\n\n"
        f"Подсказка: {get_scenario_starter_hint(get_user_scenario(user_id))}"
    )


async def show_memory_hub_message(message: Message):
    await message.answer(
        "💾 Сохранённые\n\n"
        "Здесь твои ответы, шаблоны, пресеты и память о людях.",
        reply_markup=build_memory_hub_keyboard(),
    )


async def show_settings_hub_message(message: Message, user_id: int):
    await message.answer(
        "⚙️ Настройки\n\n"
        "Здесь можно тонко настроить, как именно я собираю ответы.",
        reply_markup=build_settings_hub_keyboard(),
    )
    await message.answer(build_status_text(user_id))


async def show_coach_hub_message(message: Message):
    await message.answer(
        "🧠 Коуч\n\n"
        "Здесь ежедневный фокус, прогресс, достижения и недельный срез.",
        reply_markup=build_coach_hub_keyboard(),
    )


async def show_help_message(message: Message):
    await message.answer(
        "❓ Как пользоваться\n\n"
        "1) Выбери раздел\n"
        "2) Пришли текст\n"
        "3) Выбери следующее действие под результатом\n\n"
        "Команды тоже работают, но основной вход теперь через кнопки."
    )


async def show_quick_hub_callback(callback: CallbackQuery):
    set_user_flow_mode(callback.from_user.id, FLOW_QUICK)
    await show_callback_screen(
        callback,
        "⚡ Быстрый ответ\n\n"
        "Пришли сообщение или коротко опиши ситуацию — соберу несколько сильных вариантов.",
        build_quick_hub_keyboard(),
    )


async def show_analyze_hub_callback(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "🔍 Разбор\n\n"
        "Можно разобрать одно сообщение или целую переписку.\n"
        "Сначала выбери, что именно хочешь посмотреть.",
        build_analyze_hub_keyboard(),
    )


async def show_memory_hub_callback(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "💾 Сохранённые\n\n"
        "Здесь твои ответы, шаблоны, пресеты и память о людях.",
        build_memory_hub_keyboard(),
    )


async def show_settings_hub_callback(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "⚙️ Настройки\n\n"
        "Выбери, что хочешь настроить.",
        build_settings_hub_keyboard(),
    )

    if callback.message:
        await callback.message.answer(build_status_text(callback.from_user.id))


async def show_tone_screen(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "Выбери тон:",
        build_tone_keyboard(callback.from_user.id),
    )


async def show_goal_screen(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "Выбери цель ответа:",
        build_goal_keyboard(callback.from_user.id),
    )


async def show_variants_screen(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "Сколько вариантов показывать?",
        build_variants_keyboard(callback.from_user.id),
    )


async def show_scenario_group_screen(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "Выбери категорию сценариев:",
        build_scenario_group_keyboard(),
    )


async def show_scenario_items_screen(callback: CallbackQuery, group_key: str):
    await show_callback_screen(
        callback,
        f"{SCENARIO_GROUPS[group_key]['label']}\n\nВыбери сценарий:",
        build_scenario_items_keyboard(group_key, callback.from_user.id),
    )


async def show_analysis_mode_screen(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "Выбери режим разбора сообщения:",
        build_analysis_mode_keyboard(callback.from_user.id),
    )


async def show_dialog_mode_screen(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        "Выбери режим разбора переписки:",
        build_dialog_mode_keyboard(callback.from_user.id),
    )


async def show_people_screen(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        build_people_text(callback.from_user.id),
        build_people_keyboard(),
    )


async def show_templates_screen(callback: CallbackQuery):
    await show_callback_screen(
        callback,
        build_templates_text(callback.from_user.id),
        build_templates_keyboard(),
    )


async def run_quick_reply_and_send(message: Message, raw_user_text: str, user_id: int):
    source_text, person_name, person_note = extract_person_context(user_id, raw_user_text)

    if not source_text.strip():
        await message.answer("Сначала пришли текст.")
        return

    state = get_user_module1_state(user_id)
    scenario_key = get_user_scenario(user_id)

    tone_key = state["tone"]
    goal_key = state["goal"]
    variants_count = state["variants_count"]
    dialogue_context = get_dialogue_context(user_id)

    effective_source_text = source_text

    if person_name and person_note:
        effective_source_text = (
            f"Учитывай, что это переписка с {person_name}.\n"
            f"Что важно помнить об этом человеке: {person_note}\n\n"
            f"Ситуация:\n{source_text}"
        )

    effective_source_text = build_effective_scenario_text(effective_source_text, scenario_key)

    await message.answer("Собираю варианты...")

    try:
        result = await asyncio.to_thread(
            generate_reply_options_v2,
            effective_source_text,
            variants_count,
            tone_key,
            goal_key,
            dialogue_context,
        )

        sent = await message.answer(
            format_result_text(result),
            reply_markup=build_result_actions_keyboard(len(result["variants"])),
        )

        save_result_payload(
            sent.chat.id,
            sent.message_id,
            user_id,
            source_text,
            effective_source_text,
            dialogue_context,
            tone_key,
            goal_key,
            scenario_key,
            variants_count,
            result,
        )

        add_to_history(user_id, "Пользователь", source_text)
        add_to_history(user_id, "Бот", result["best_variant_text"])
        register_user_event(user_id, "generation")

    except Exception as e:
        print(f"Ошибка quick reply: {e}")
        await message.answer("Не получилось собрать варианты. Попробуй ещё раз.")


async def run_builder_and_send(message: Message, user_text: str, user_id: int):
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Собираю готовое сообщение...")

    try:
        final_message = await asyncio.to_thread(
            build_message_from_brief,
            user_text,
            dialogue_context,
        )

        await message.answer(
            f"Готовое сообщение:\n\n{final_message}",
            reply_markup=build_quick_hub_keyboard(),
        )

    except Exception as e:
        print(f"Ошибка builder: {e}")
        await message.answer("Не получилось собрать сообщение. Попробуй ещё раз.")


async def run_message_analysis_and_send(message: Message, user_text: str, user_id: int):
    mode = get_user_analysis_mode(user_id)
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Смотрю на сообщение...")

    try:
        analysis_text = await asyncio.to_thread(
            analyze_single_message_v2,
            user_text,
            mode,
            dialogue_context,
        )

        register_user_event(user_id, "analysis")

        await message.answer(
            f"{analysis_text}",
            reply_markup=build_analyze_hub_keyboard(),
        )

    except Exception as e:
        print(f"Ошибка message analysis: {e}")
        await message.answer("Не получилось разобрать сообщение. Попробуй ещё раз.")


async def run_dialog_analysis_and_send(message: Message, user_text: str, user_id: int):
    mode = get_user_dialog_analysis_mode(user_id)
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Смотрю на переписку...")

    try:
        analysis_text = await asyncio.to_thread(
            analyze_dialog_v2,
            user_text,
            mode,
            dialogue_context,
        )

        register_user_event(user_id, "dialog")

        await message.answer(
            f"{analysis_text}",
            reply_markup=build_analyze_hub_keyboard(),
        )

    except Exception as e:
        print(f"Ошибка dialog analysis: {e}")
        await message.answer("Не получилось разобрать переписку. Попробуй ещё раз.")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id

    user_dialogues[user_id] = []
    user_module1_settings[user_id] = get_default_module1_state()
    user_analysis_modes[user_id] = "general"
    user_dialog_analysis_modes[user_id] = "general"
    user_scenarios[user_id] = DEFAULT_SCENARIO_KEY
    user_flow_modes[user_id] = FLOW_QUICK

    apply_saved_preset_if_exists(user_id)
    await show_start_screen(message)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await show_help_message(message)


@dp.message(Command("saved"))
async def cmd_saved(message: Message):
    await message.answer(build_saved_replies_text(message.from_user.id))


@dp.message(Command("templates"))
async def cmd_templates(message: Message):
    await message.answer(build_templates_text(message.from_user.id))


@dp.message(Command("save_preset"))
async def cmd_save_preset(message: Message):
    user_id = message.from_user.id
    state = get_user_module1_state(user_id)

    save_user_preset(
        user_id,
        {
            "tone": state["tone"],
            "goal": state["goal"],
            "variants_count": state["variants_count"],
            "scenario": get_user_scenario(user_id),
        },
    )

    await message.answer("Готово — текущие настройки сохранены как твой пресет.")


@dp.message(Command("my_preset"))
async def cmd_my_preset(message: Message):
    user_id = message.from_user.id

    if not apply_saved_preset_if_exists(user_id):
        await message.answer("Сохранённого пресета пока нет.")
        return

    await message.answer(
        "Твой пресет загружен.\n\n"
        f"{build_status_text(user_id)}"
    )


@dp.message(Command("coach"))
async def cmd_coach(message: Message):
    register_user_event(message.from_user.id, "coach")
    await message.answer(build_coach_today_text(message.from_user.id))


@dp.message(Command("progress"))
async def cmd_progress(message: Message):
    await message.answer(build_progress_text(message.from_user.id))


@dp.message(Command("base"))
async def cmd_base(message: Message):
    source_text = extract_command_payload_or_reply_text(message)

    if not source_text:
        await message.answer(
            "Напиши так:\n"
            "/base твой текст\n\n"
            "Или ответь этой командой на сообщение."
        )
        return

    dialogue_context = get_dialogue_context(message.from_user.id)

    await message.answer("Сейчас дам один базовый вариант...")

    try:
        reply_text = await asyncio.to_thread(
            generate_baseline_reply,
            source_text,
            dialogue_context,
        )

        await message.answer(f"Базовый вариант:\n\n{reply_text}")

    except Exception as e:
        print(f"Ошибка /base: {e}")
        await message.answer("Не получилось получить ответ. Попробуй ещё раз.")


@dp.message(Command("analyze"))
async def cmd_analyze(message: Message):
    source_text = extract_command_payload_or_reply_text(message)

    if not source_text:
        await show_analyze_hub_message(message)
        return

    set_user_flow_mode(message.from_user.id, FLOW_ANALYZE_MESSAGE)
    await run_message_analysis_and_send(message, source_text, message.from_user.id)


@dp.message(Command("dialog"))
async def cmd_dialog(message: Message):
    source_text = extract_command_payload_or_reply_text(message)

    if not source_text:
        await show_analyze_hub_message(message)
        return

    set_user_flow_mode(message.from_user.id, FLOW_ANALYZE_DIALOG)
    await run_dialog_analysis_and_send(message, source_text, message.from_user.id)


@dp.message(F.text == "⚡ Быстрый ответ")
async def menu_quick(message: Message):
    await show_quick_hub_message(message, message.from_user.id)


@dp.message(F.text == "🔍 Разбор")
async def menu_analyze(message: Message):
    await show_analyze_hub_message(message)


@dp.message(F.text == "🎭 Сценарии")
async def menu_scenarios(message: Message):
    await show_scenarios_hub_message(message, message.from_user.id)


@dp.message(F.text == "💾 Сохранённые")
async def menu_memory(message: Message):
    await show_memory_hub_message(message)


@dp.message(F.text == "⚙️ Настройки")
async def menu_settings(message: Message):
    await show_settings_hub_message(message, message.from_user.id)


@dp.message(F.text == "🧠 Коуч")
async def menu_coach(message: Message):
    await show_coach_hub_message(message)


@dp.message(F.text == "❓ Помощь")
async def menu_help(message: Message):
    await show_help_message(message)


@dp.callback_query(F.data == "nav:main")
async def cb_nav_main(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Главное меню снова перед тобой.",
            reply_markup=build_main_menu(),
        )


@dp.callback_query(F.data == "hub:quick")
async def cb_hub_quick(callback: CallbackQuery):
    await callback.answer()
    await show_quick_hub_callback(callback)


@dp.callback_query(F.data == "hub:analyze")
async def cb_hub_analyze(callback: CallbackQuery):
    await callback.answer()
    await show_analyze_hub_callback(callback)


@dp.callback_query(F.data == "hub:memory")
async def cb_hub_memory(callback: CallbackQuery):
    await callback.answer()
    await show_memory_hub_callback(callback)


@dp.callback_query(F.data == "hub:settings")
async def cb_hub_settings(callback: CallbackQuery):
    await callback.answer()
    await show_settings_hub_callback(callback)


@dp.callback_query(F.data == "flow:quick")
async def cb_flow_quick(callback: CallbackQuery):
    set_user_flow_mode(callback.from_user.id, FLOW_QUICK)
    await callback.answer("Жду текст")
    await show_callback_screen(
        callback,
        "Пришли сообщение или ситуацию — соберу сильные варианты.",
        build_quick_hub_keyboard(),
    )


@dp.callback_query(F.data == "flow:builder")
async def cb_flow_builder(callback: CallbackQuery):
    set_user_flow_mode(callback.from_user.id, FLOW_BUILDER)
    await callback.answer("Жду задачу")
    await show_callback_screen(
        callback,
        "Напиши коротко, что хочешь сказать — я превращу это в готовое сообщение.",
        build_quick_hub_keyboard(),
    )


@dp.callback_query(F.data == "flow:an_message")
async def cb_flow_an_message(callback: CallbackQuery):
    set_user_flow_mode(callback.from_user.id, FLOW_ANALYZE_MESSAGE)
    await callback.answer("Жду сообщение")
    await show_callback_screen(
        callback,
        "Пришли одно сообщение — разберу, что в нём читается и что лучше делать дальше.",
        build_analyze_hub_keyboard(),
    )


@dp.callback_query(F.data == "flow:an_dialog")
async def cb_flow_an_dialog(callback: CallbackQuery):
    set_user_flow_mode(callback.from_user.id, FLOW_ANALYZE_DIALOG)
    await callback.answer("Жду переписку")
    await show_callback_screen(
        callback,
        "Пришли переписку целиком.\n\n"
        "Лучше в формате:\n"
        "Я: ...\n"
        "Он/Она: ...",
        build_analyze_hub_keyboard(),
    )


@dp.callback_query(F.data == "open:analysis_modes")
async def cb_open_analysis_modes(callback: CallbackQuery):
    await callback.answer()
    await show_analysis_mode_screen(callback)


@dp.callback_query(F.data == "open:dialog_modes")
async def cb_open_dialog_modes(callback: CallbackQuery):
    await callback.answer()
    await show_dialog_mode_screen(callback)


@dp.callback_query(F.data == "set:tones")
async def cb_set_tones(callback: CallbackQuery):
    await callback.answer()
    await show_tone_screen(callback)


@dp.callback_query(F.data == "set:goals")
async def cb_set_goals(callback: CallbackQuery):
    await callback.answer()
    await show_goal_screen(callback)


@dp.callback_query(F.data == "set:variants")
async def cb_set_variants(callback: CallbackQuery):
    await callback.answer()
    await show_variants_screen(callback)


@dp.callback_query(F.data == "set:scenarios")
async def cb_set_scenarios(callback: CallbackQuery):
    await callback.answer()
    await show_scenario_group_screen(callback)


@dp.callback_query(F.data.startswith("sc_group:"))
async def cb_scenario_group(callback: CallbackQuery):
    if not callback.data:
        return

    group_key = callback.data.split(":", 1)[1]

    if group_key not in SCENARIO_GROUPS:
        await callback.answer("Категория не найдена")
        return

    await callback.answer()
    await show_scenario_items_screen(callback, group_key)


@dp.callback_query(F.data.startswith("an_mode:"))
async def cb_analysis_mode(callback: CallbackQuery):
    if not callback.data:
        return

    mode = callback.data.split(":", 1)[1]

    if mode not in ANALYSIS_MODE_LABELS:
        await callback.answer("Неизвестный режим")
        return

    user_analysis_modes[callback.from_user.id] = mode
    await callback.answer("Сохранил")
    await show_analysis_mode_screen(callback)


@dp.callback_query(F.data.startswith("dlg_mode:"))
async def cb_dialog_mode(callback: CallbackQuery):
    if not callback.data:
        return

    mode = callback.data.split(":", 1)[1]

    if mode not in DIALOG_ANALYSIS_MODE_LABELS:
        await callback.answer("Неизвестный режим")
        return

    user_dialog_analysis_modes[callback.from_user.id] = mode
    await callback.answer("Сохранил")
    await show_dialog_mode_screen(callback)


@dp.callback_query(F.data.startswith("m1_tone:"))
async def cb_tone(callback: CallbackQuery):
    if not callback.data:
        return

    tone_key = callback.data.split(":", 1)[1]
    state = get_user_module1_state(callback.from_user.id)

    if tone_key == "neutral":
        state["tone"] = DEFAULT_TONE
    elif tone_key in TONE_OPTIONS:
        state["tone"] = tone_key
    else:
        await callback.answer("Неизвестный тон")
        return

    await callback.answer("Готово")
    await show_tone_screen(callback)


@dp.callback_query(F.data.startswith("m1_goal:"))
async def cb_goal(callback: CallbackQuery):
    if not callback.data:
        return

    goal_key = callback.data.split(":", 1)[1]

    if goal_key not in GOAL_OPTIONS:
        await callback.answer("Неизвестная цель")
        return

    state = get_user_module1_state(callback.from_user.id)
    state["goal"] = goal_key

    await callback.answer("Готово")
    await show_goal_screen(callback)


@dp.callback_query(F.data.startswith("m1_variants:"))
async def cb_variants(callback: CallbackQuery):
    if not callback.data:
        return

    count = callback.data.split(":", 1)[1]
    state = get_user_module1_state(callback.from_user.id)
    state["variants_count"] = normalize_variants_count(count)

    await callback.answer("Готово")
    await show_variants_screen(callback)


@dp.callback_query(F.data.startswith("sc_mode:"))
async def cb_scenario_mode(callback: CallbackQuery):
    if not callback.data:
        return

    scenario_key = callback.data.split(":", 1)[1]

    if scenario_key not in SCENARIO_OPTIONS:
        await callback.answer("Неизвестный сценарий")
        return

    user_id = callback.from_user.id
    user_scenarios[user_id] = scenario_key

    defaults = get_scenario_defaults(scenario_key)
    state = get_user_module1_state(user_id)

    apply_tone_to_state(state, defaults["tone"])

    if defaults["goal"] in GOAL_OPTIONS:
        state["goal"] = defaults["goal"]

    state["variants_count"] = normalize_variants_count(defaults["variants"])

    await callback.answer("Сценарий применён")

    await show_callback_screen(
        callback,
        f"Сценарий: {get_scenario_label(scenario_key)}\n\n"
        f"{build_status_text(user_id)}\n\n"
        f"Подсказка: {get_scenario_starter_hint(scenario_key)}",
        build_quick_hub_keyboard(),
    )


@dp.callback_query(F.data == "settings:reset_history")
async def cb_reset_history(callback: CallbackQuery):
    user_dialogues[callback.from_user.id] = []
    await callback.answer("Готово")
    await show_callback_screen(
        callback,
        "Контекст очищен.\n\n"
        "Если хочешь, теперь можно начать заново.",
        build_settings_hub_keyboard(),
    )


@dp.callback_query(F.data == "memory:saved")
async def cb_memory_saved(callback: CallbackQuery):
    await callback.answer()
    await show_callback_screen(
        callback,
        build_saved_replies_text(callback.from_user.id),
        build_templates_keyboard(),
    )


@dp.callback_query(F.data == "memory:templates")
async def cb_memory_templates(callback: CallbackQuery):
    await callback.answer()
    await show_templates_screen(callback)


@dp.callback_query(F.data == "memory:people")
async def cb_memory_people(callback: CallbackQuery):
    await callback.answer()
    await show_people_screen(callback)


@dp.callback_query(F.data == "memory:add_person")
async def cb_memory_add_person(callback: CallbackQuery):
    set_user_flow_mode(callback.from_user.id, FLOW_PERSON_NOTE)
    await callback.answer("Жду заметку")
    await show_callback_screen(
        callback,
        "Пришли заметку в формате:\n"
        "Имя: что важно помнить",
        build_people_keyboard(),
    )


@dp.callback_query(F.data == "memory:my_preset")
async def cb_memory_my_preset(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if not apply_saved_preset_if_exists(user_id):
        await show_callback_screen(
            callback,
            "Сохранённого пресета пока нет.",
            build_memory_hub_keyboard(),
        )
        return

    await show_callback_screen(
        callback,
        f"Твой пресет загружен.\n\n{build_status_text(user_id)}",
        build_memory_hub_keyboard(),
    )


@dp.callback_query(F.data == "memory:save_preset")
async def cb_memory_save_preset(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    state = get_user_module1_state(user_id)

    save_user_preset(
        user_id,
        {
            "tone": state["tone"],
            "goal": state["goal"],
            "variants_count": state["variants_count"],
            "scenario": get_user_scenario(user_id),
        },
    )

    await show_callback_screen(
        callback,
        "Готово — текущие настройки сохранены как твой пресет.",
        build_memory_hub_keyboard(),
    )


@dp.callback_query(F.data == "coach:today")
async def cb_coach_today(callback: CallbackQuery):
    await callback.answer()
    register_user_event(callback.from_user.id, "coach")
    await show_callback_screen(
        callback,
        build_coach_today_text(callback.from_user.id),
        build_coach_hub_keyboard(),
    )


@dp.callback_query(F.data == "coach:progress")
async def cb_coach_progress(callback: CallbackQuery):
    await callback.answer()
    await show_callback_screen(
        callback,
        build_progress_text(callback.from_user.id),
        build_coach_hub_keyboard(),
    )


@dp.callback_query(F.data == "coach:week")
async def cb_coach_week(callback: CallbackQuery):
    await callback.answer()
    await show_callback_screen(
        callback,
        build_week_review_text(callback.from_user.id),
        build_coach_hub_keyboard(),
    )


@dp.callback_query(F.data == "m1_pick_best")
async def cb_pick_best(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(callback.message.chat.id, callback.message.message_id)

    if not payload:
        await callback.answer("Этот результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    await callback.answer("Готово")
    await callback.message.answer(payload["best_variant_text"])


@dp.callback_query(F.data == "m1_regen")
async def cb_regen(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(callback.message.chat.id, callback.message.message_id)

    if not payload:
        await callback.answer("Этот результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    await callback.answer("Обновляю...")

    try:
        new_result = await asyncio.to_thread(
            generate_reply_options_v2,
            payload["effective_source_text"],
            payload["variants_count"],
            payload["tone_key"],
            payload["goal_key"],
            payload["dialogue_context"],
        )

        try:
            await callback.message.edit_text(
                format_result_text(new_result),
                reply_markup=build_result_actions_keyboard(len(new_result["variants"])),
            )
            target_message = callback.message
        except Exception:
            target_message = await callback.message.answer(
                format_result_text(new_result),
                reply_markup=build_result_actions_keyboard(len(new_result["variants"])),
            )

        save_result_payload(
            target_message.chat.id,
            target_message.message_id,
            payload["user_id"],
            payload["source_text"],
            payload["effective_source_text"],
            payload["dialogue_context"],
            payload["tone_key"],
            payload["goal_key"],
            payload["scenario_key"],
            payload["variants_count"],
            new_result,
        )

    except Exception as e:
        print(f"Ошибка regen: {e}")
        await callback.message.answer("Не получилось собрать ещё варианты.")


@dp.callback_query(F.data == "m1_compare")
async def cb_compare(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(callback.message.chat.id, callback.message.message_id)

    if not payload:
        await callback.answer("Этот результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    await callback.answer("Сравниваю...")

    try:
        compare_text = await asyncio.to_thread(
            compare_reply_variants,
            payload["variants"],
            payload["dialogue_context"],
        )

        await callback.message.answer(compare_text)

    except Exception as e:
        print(f"Ошибка compare: {e}")
        await callback.message.answer("Не получилось сравнить варианты.")


@dp.callback_query(F.data == "result_tools:open")
async def cb_result_tools_open(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(callback.message.chat.id, callback.message.message_id)

    if not payload:
        await callback.answer("Этот результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    await callback.answer()
    await callback.message.answer(
        "Что проверить у лучшего варианта?",
        reply_markup=build_result_tools_keyboard(),
    )


@dp.callback_query(F.data.startswith("result_tool:"))
async def cb_result_tool(callback: CallbackQuery):
    if not callback.message or not callback.data:
        return

    payload = get_result_payload(callback.message.chat.id, callback.message.message_id)

    if not payload:
        await callback.answer("Этот результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    tool_key = callback.data.split(":", 1)[1]
    mode_map = {
        "before_send": "before_send",
        "risk": "risk",
        "reaction": "reaction",
    }

    if tool_key not in mode_map:
        await callback.answer("Неизвестная проверка")
        return

    await callback.answer("Смотрю...")

    try:
        text = await asyncio.to_thread(
            analyze_single_message_v2,
            payload["best_variant_text"],
            mode_map[tool_key],
            payload["dialogue_context"],
        )

        await callback.message.answer(
            text,
            reply_markup=build_result_tools_keyboard(),
        )

    except Exception as e:
        print(f"Ошибка result tool: {e}")
        await callback.message.answer("Не получилось проверить этот вариант.")


@dp.callback_query(F.data == "m1_save_best")
async def cb_save_best(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(callback.message.chat.id, callback.message.message_id)

    if not payload:
        await callback.answer("Этот результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    total = save_reply_to_memory(callback.from_user.id, payload["best_variant_text"])

    if total == 0:
        await callback.answer("Не удалось сохранить")
        return

    register_user_event(callback.from_user.id, "save")
    await callback.answer("Сохранил")
    await callback.message.answer("Сохранил. Теперь это у тебя под рукой.")


@dp.callback_query(F.data == "m1_save_template")
async def cb_save_template(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(callback.message.chat.id, callback.message.message_id)

    if not payload:
        await callback.answer("Этот результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    total = save_template_to_memory(callback.from_user.id, payload["best_variant_text"])

    if total == 0:
        await callback.answer("Не удалось сохранить")
        return

    await callback.answer("Шаблон сохранён")
    await callback.message.answer("Готово. Лучший вариант сохранён как шаблон.")


@dp.callback_query(F.data.startswith("m1_pick:"))
async def cb_pick_variant(callback: CallbackQuery):
    if not callback.message or not callback.data:
        return

    payload = get_result_payload(callback.message.chat.id, callback.message.message_id)

    if not payload:
        await callback.answer("Этот результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    raw_index = callback.data.split(":", 1)[1]

    try:
        index = int(raw_index)
    except ValueError:
        await callback.answer("Неверный номер")
        return

    if index < 1 or index > len(payload["variants"]):
        await callback.answer("Вариант не найден")
        return

    await callback.answer("Готово")
    await callback.message.answer(payload["variants"][index - 1])


@dp.message(F.text.startswith("/"))
async def unknown_command(message: Message):
    await message.answer(
        "Не знаю такую команду.\n\n"
        "Нажми кнопку снизу или открой /help."
    )


@dp.message(F.text)
async def handle_text_message(message: Message):
    user_text = (message.text or "").strip()

    if not user_text:
        await message.answer("Сначала пришли текст.")
        return

    user_id = message.from_user.id
    flow_mode = get_user_flow_mode(user_id)

    if flow_mode == FLOW_PERSON_NOTE:
        ok, person_name = upsert_person_note(user_id, user_text)

        if not ok:
            await message.answer(
                "Не понял формат.\n\n"
                "Напиши так:\n"
                "Имя: что важно помнить"
            )
            return

        set_user_flow_mode(user_id, FLOW_QUICK)
        await message.answer(
            f"Запомнил: {person_name}.\n\n"
            "Теперь можно использовать это в быстром ответе:\n"
            f"@{person_name}: твоя ситуация"
        )
        return

    if flow_mode == FLOW_BUILDER:
        await run_builder_and_send(message, user_text, user_id)
        return

    if flow_mode == FLOW_ANALYZE_MESSAGE:
        await run_message_analysis_and_send(message, user_text, user_id)
        return

    if flow_mode == FLOW_ANALYZE_DIALOG:
        await run_dialog_analysis_and_send(message, user_text, user_id)
        return

    await run_quick_reply_and_send(message, user_text, user_id)


async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())