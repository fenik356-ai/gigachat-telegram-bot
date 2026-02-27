import asyncio
import os

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
    get_saved_replies,
    get_user_engagement_stats,
    get_user_preset,
    register_user_event,
    save_reply_to_memory,
    save_user_preset,
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

FLOW_QUICK = "quick_reply"
FLOW_ANALYZE_MESSAGE = "analyze_message"
FLOW_ANALYZE_DIALOG = "analyze_dialog"

ANALYSIS_MODE_LABELS = {
    "general": "Общий",
    "meaning": "Смысл",
    "risk": "Риск",
    "before_send": "Перед отправкой",
    "reaction": "Реакция",
}

DIALOG_ANALYSIS_MODE_LABELS = {
    "general": "Общий",
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
            "restore_contact",
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
    clean_text = " ".join(text.split()).strip()

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


def extract_command_payload_or_reply_text(message: Message) -> str:
    raw_text = message.text or ""
    parts = raw_text.split(maxsplit=1)

    if len(parts) > 1 and parts[1].strip():
        return parts[1].strip()

    reply_to = message.reply_to_message
    if reply_to and reply_to.text and reply_to.text.strip():
        return reply_to.text.strip()

    return ""


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
                KeyboardButton(text="🔍 Анализ"),
            ],
            [
                KeyboardButton(text="🎭 Сценарии"),
                KeyboardButton(text="💾 Память"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="🧠 Личный кабинет"),
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
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Настроить ответ",
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


def build_analysis_hub_keyboard() -> InlineKeyboardMarkup:
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
                    text="💾 Сохранённые",
                    callback_data="memory:saved",
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
                ),
                InlineKeyboardButton(
                    text="🤖 AI-коуч",
                    callback_data="memory:coach",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📈 Прогресс",
                    callback_data="memory:progress",
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


def build_locker_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 AI-коуч",
                    callback_data="memory:coach",
                ),
                InlineKeyboardButton(
                    text="📈 Прогресс",
                    callback_data="memory:progress",
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


def build_tone_keyboard(user_id: int) -> InlineKeyboardMarkup:
    state = get_user_module1_state(user_id)
    current_tone = state["tone"]

    def tone_text(key: str, label: str) -> str:
        return f"✅ {label}" if current_tone == key else label

    def normal_text() -> str:
        return "✅ Обычный" if current_tone == DEFAULT_TONE else "Обычный"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=normal_text(),
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
    state = get_user_module1_state(user_id)
    current_variants = state["variants_count"]

    def item_text(count: int) -> str:
        return f"✅ {count}" if current_variants == count else str(count)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=item_text(3),
                    callback_data="m1_variants:3",
                ),
                InlineKeyboardButton(
                    text=item_text(4),
                    callback_data="m1_variants:4",
                ),
                InlineKeyboardButton(
                    text=item_text(5),
                    callback_data="m1_variants:5",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=item_text(6),
                    callback_data="m1_variants:6",
                ),
                InlineKeyboardButton(
                    text=item_text(7),
                    callback_data="m1_variants:7",
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


def build_scenario_groups_keyboard() -> InlineKeyboardMarkup:
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
    group = SCENARIO_GROUPS[group_key]

    rows = []

    for scenario_key in group["items"]:
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
                text="⬅️ К категориям",
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
    current_mode = get_user_analysis_mode(user_id)

    def item_text(key: str) -> str:
        label = ANALYSIS_MODE_LABELS[key]
        return f"✅ {label}" if current_mode == key else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=item_text("general"),
                    callback_data="an_mode:general",
                ),
                InlineKeyboardButton(
                    text=item_text("meaning"),
                    callback_data="an_mode:meaning",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=item_text("risk"),
                    callback_data="an_mode:risk",
                ),
                InlineKeyboardButton(
                    text=item_text("before_send"),
                    callback_data="an_mode:before_send",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=item_text("reaction"),
                    callback_data="an_mode:reaction",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К анализу",
                    callback_data="hub:analysis",
                )
            ],
        ]
    )


def build_dialog_mode_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current_mode = get_user_dialog_analysis_mode(user_id)

    def item_text(key: str) -> str:
        label = DIALOG_ANALYSIS_MODE_LABELS[key]
        return f"✅ {label}" if current_mode == key else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=item_text("general"),
                    callback_data="dlg_mode:general",
                ),
                InlineKeyboardButton(
                    text=item_text("dynamics"),
                    callback_data="dlg_mode:dynamics",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=item_text("interest"),
                    callback_data="dlg_mode:interest",
                ),
                InlineKeyboardButton(
                    text=item_text("mistakes"),
                    callback_data="dlg_mode:mistakes",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=item_text("next_step"),
                    callback_data="dlg_mode:next_step",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К анализу",
                    callback_data="hub:analysis",
                )
            ],
        ]
    )


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
                    text="⚡ К быстрому ответу",
                    callback_data="hub:quick",
                ),
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="nav:main",
                ),
            ],
        ]
    )


def build_result_keyboard(variants_count: int) -> InlineKeyboardMarkup:
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
                text="⭐ Сохранить",
                callback_data="m1_save_best",
            ),
            InlineKeyboardButton(
                text="🔎 Проверить",
                callback_data="result_tools:open",
            ),
        ],
    ]

    pick_buttons = []
    for index in range(1, variants_count + 1):
        pick_buttons.append(
            InlineKeyboardButton(
                text=str(index),
                callback_data=f"m1_pick:{index}",
            )
        )

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


def build_status_text(user_id: int) -> str:
    state = get_user_module1_state(user_id)
    tone_key = state["tone"]
    goal_key = state["goal"]
    variants_count = state["variants_count"]
    scenario_key = get_user_scenario(user_id)

    tone_label = "Обычный" if tone_key == DEFAULT_TONE else get_tone_label(tone_key)

    return (
        "Сейчас так:\n"
        f"• Тон: {tone_label}\n"
        f"• Цель: {get_goal_label(goal_key)}\n"
        f"• Сценарий: {get_scenario_label(scenario_key)}\n"
        f"• Вариантов: {variants_count}"
    )


def build_scenario_hint_text(user_id: int) -> str:
    scenario_key = get_user_scenario(user_id)
    return f"Подсказка: {get_scenario_starter_hint(scenario_key)}"


def build_analysis_status_text(user_id: int) -> str:
    mode = get_user_analysis_mode(user_id)
    return f"Режим анализа сообщения: {ANALYSIS_MODE_LABELS.get(mode, 'Общий')}"


def build_dialog_analysis_status_text(user_id: int) -> str:
    mode = get_user_dialog_analysis_mode(user_id)
    return f"Режим анализа переписки: {DIALOG_ANALYSIS_MODE_LABELS.get(mode, 'Общий')}"


def build_progress_text(user_id: int) -> str:
    stats = get_user_engagement_stats(user_id)

    achievement_lines = ["• Пока без достижений — просто продолжай."]
    if stats["achievements"]:
        achievement_lines = [f"• {item}" for item in stats["achievements"]]

    return (
        "Твой прогресс:\n"
        f"• Активных дней: {stats['total_active_days']}\n"
        f"• Текущая серия: {stats['current_streak']}\n"
        f"• Лучшая серия: {stats['best_streak']}\n"
        f"• Генераций: {stats['generation_count']}\n"
        f"• Разборов сообщений: {stats['analysis_count']}\n"
        f"• Разборов переписки: {stats['dialog_count']}\n"
        f"• Сохранённых ответов: {stats['saved_replies_count']}\n"
        f"• Открытий коуча: {stats['coach_view_count']}\n\n"
        "Достижения:\n"
        + "\n".join(achievement_lines)
    )


def build_coach_focus(stats: dict) -> str:
    if stats["generation_count"] < 5:
        return "Сделай 3 генерации на реальных сообщениях и сравни, какой вариант сильнее."
    if stats["saved_replies_count"] < 3:
        return "Сохрани хотя бы 1 сильный ответ через кнопку ⭐ Сохранить."
    if stats["analysis_count"] + stats["dialog_count"] < 5:
        return "Разбери 1 сообщение или 1 переписку, чтобы улучшить следующий ответ."
    if stats["current_streak"] < 3:
        return "Зайди завтра снова и удержи серию активности."
    return "Пройди сегодня полный цикл: анализ → быстрый ответ → сохранить лучший."


def build_coach_tip(user_id: int) -> str:
    scenario_key = get_user_scenario(user_id)

    tips = {
        "neutral": "Сначала описывай ситуацию коротко — так ответы получаются точнее.",
        "dating_intro": "В знакомствах сильнее работают лёгкие фразы, на которые легко ответить.",
        "restore_contact": "После паузы лучше мягкий вход, а не длинные оправдания.",
        "business": "В деловой переписке ясность почти всегда сильнее креатива.",
        "sales": "В продажах лучше снижать трение, а не давить.",
        "support": "Сначала снимай напряжение, потом веди к решению.",
        "soft_decline": "Хороший отказ — короткий, вежливый и ясный.",
        "boundaries": "Границы звучат сильнее, когда ты спокоен и прям.",
        "hard_talk": "В сложном разговоре убирай лишние эмоции из формулировки.",
        "rescue_chat": "Чтобы оживить чат, лучше вернуть лёгкость, а не дожимать.",
        "first_message": "Первое сообщение должно быть простым для ответа.",
        "close_result": "Если нужен результат — предлагай один конкретный следующий шаг.",
        "difficult_person": "Со сложным человеком сильнее короткий и предсказуемый ответ.",
    }

    return tips.get(scenario_key, tips["neutral"])


def build_daily_coach_text(user_id: int) -> str:
    stats = get_user_engagement_stats(user_id)
    scenario_label = get_scenario_label(get_user_scenario(user_id))
    saved_replies = get_saved_replies(user_id)

    answer_of_day = (
        saved_replies[0]
        if saved_replies
        else "Пока нет сохранённого ответа дня. Сначала сгенерируй варианты и сохрани лучший."
    )

    return (
        "AI-коуч на сегодня:\n"
        f"• Текущий сценарий: {scenario_label}\n"
        f"• Серия: {stats['current_streak']}\n"
        f"• Активных дней: {stats['total_active_days']}\n\n"
        f"Фокус:\n• {build_coach_focus(stats)}\n\n"
        f"Мини-обучение:\n• {build_coach_tip(user_id)}\n\n"
        f"Ответ дня:\n• {answer_of_day}"
    )


def format_saved_replies_text(replies: list[str]) -> str:
    if not replies:
        return (
            "Пока пусто.\n\n"
            "Сначала сгенерируй варианты и нажми ⭐ Сохранить."
        )

    lines = ["Сохранённые удачные ответы:"]
    for index, item in enumerate(replies, start=1):
        lines.append(f"\n{index}) {item}")

    return "\n".join(lines)


def format_module1_result(result: dict) -> str:
    lines = ["Вот что можно отправить:\n"]

    for index, variant in enumerate(result["variants"], start=1):
        lines.append(f"{index}. {variant}")

    lines.append("")
    lines.append(f"Лучший сейчас — №{result['best_index']}")
    lines.append(f"Почему: {result['best_reason']}")

    return "\n".join(lines)


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
    key = make_result_key(chat_id, message_id)

    result_message_payloads[key] = {
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


def get_result_payload(chat_id: int, message_id: int):
    return result_message_payloads.get(make_result_key(chat_id, message_id))


async def safe_remove_result_markup(callback: CallbackQuery):
    if not callback.message:
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def send_start_screen(message: Message):
    user_id = message.from_user.id
    set_user_flow_mode(user_id, FLOW_QUICK)

    await message.answer(
        "Привет. Я помогу быстро ответить, разобрать сообщение или посмотреть на переписку целиком.\n\n"
        "Выбери раздел снизу. Если хочешь сразу начать — просто отправь текст.",
        reply_markup=build_main_menu(),
    )


async def send_quick_hub(message: Message, user_id: int):
    set_user_flow_mode(user_id, FLOW_QUICK)

    await message.answer(
        "⚡ Быстрый ответ\n\n"
        "Пришли сообщение или коротко опиши ситуацию — я предложу несколько сильных вариантов.",
        reply_markup=build_quick_hub_keyboard(),
    )


async def send_analysis_hub(message: Message, user_id: int):
    await message.answer(
        "🔍 Анализ\n\n"
        "Здесь можно разобрать одно сообщение или целую переписку.\n"
        "Сначала выбери, что именно хочешь посмотреть.",
        reply_markup=build_analysis_hub_keyboard(),
    )


async def send_scenarios_hub(message: Message, user_id: int):
    await message.answer(
        "🎭 Сценарии\n\n"
        "Выбери категорию. Сценарий станет контекстом для быстрых ответов.",
        reply_markup=build_scenario_groups_keyboard(),
    )

    await message.answer(build_status_text(user_id))


async def send_memory_hub(message: Message, user_id: int):
    await message.answer(
        "💾 Память\n\n"
        "Здесь твои сохранённые ответы, пресеты и быстрый доступ к личным данным.",
        reply_markup=build_memory_hub_keyboard(),
    )


async def send_settings_hub(message: Message, user_id: int):
    await message.answer(
        "⚙️ Настройки\n\n"
        "Здесь можно тонко настроить, как именно я генерирую ответы.",
        reply_markup=build_settings_hub_keyboard(),
    )

    await message.answer(build_status_text(user_id))


async def send_locker_hub(message: Message, user_id: int):
    await message.answer(
        "🧠 Личный кабинет\n\n"
        "Здесь AI-коуч, прогресс и мотивация возвращаться к боту каждый день.",
        reply_markup=build_locker_hub_keyboard(),
    )


async def send_help_screen(message: Message):
    await message.answer(
        "❓ Как пользоваться\n\n"
        "1) Нажми нужный раздел снизу\n"
        "2) Отправь текст\n"
        "3) Выбери следующее действие под результатом\n\n"
        "Если удобнее, команды тоже работают: /start, /help, /saved, /coach, /progress."
    )


async def send_main_menu_hint(target: Message | CallbackQuery, user_id: int):
    if isinstance(target, Message):
        await target.answer(
            "Ты в главном меню. Выбери раздел снизу.",
            reply_markup=build_main_menu(),
        )
    else:
        if target.message:
            await target.message.answer(
                "Ты в главном меню. Выбери раздел снизу.",
                reply_markup=build_main_menu(),
            )


async def run_message_analysis_and_send(message: Message, source_text: str, user_id: int):
    mode = get_user_analysis_mode(user_id)
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Смотрю на сообщение...")

    try:
        analysis_text = await asyncio.to_thread(
            analyze_single_message_v2,
            source_text,
            mode,
            dialogue_context,
        )

        register_user_event(user_id, "analysis")

        await message.answer(
            f"{build_analysis_status_text(user_id)}\n\n{analysis_text}",
            reply_markup=build_analysis_hub_keyboard(),
        )
    except Exception as e:
        print(f"Ошибка анализа сообщения: {e}")
        await message.answer(
            "Не получилось разобрать сообщение. Попробуй ещё раз чуть позже."
        )


async def run_dialog_analysis_and_send(message: Message, dialog_text: str, user_id: int):
    mode = get_user_dialog_analysis_mode(user_id)
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Смотрю на переписку...")

    try:
        analysis_text = await asyncio.to_thread(
            analyze_dialog_v2,
            dialog_text,
            mode,
            dialogue_context,
        )

        register_user_event(user_id, "dialog")

        await message.answer(
            f"{build_dialog_analysis_status_text(user_id)}\n\n{analysis_text}",
            reply_markup=build_analysis_hub_keyboard(),
        )
    except Exception as e:
        print(f"Ошибка анализа переписки: {e}")
        await message.answer(
            "Не получилось разобрать переписку. Попробуй ещё раз чуть позже."
        )


async def run_quick_reply_and_send(message: Message, user_text: str, user_id: int):
    state = get_user_module1_state(user_id)
    scenario_key = get_user_scenario(user_id)

    tone_key = state["tone"]
    goal_key = state["goal"]
    variants_count = state["variants_count"]
    dialogue_context = get_dialogue_context(user_id)

    effective_user_text = build_effective_scenario_text(user_text, scenario_key)

    await message.answer("Собираю варианты...")

    try:
        result = await asyncio.to_thread(
            generate_reply_options_v2,
            effective_user_text,
            variants_count,
            tone_key,
            goal_key,
            dialogue_context,
        )

        sent_result_message = await message.answer(
            format_module1_result(result),
            reply_markup=build_result_keyboard(len(result["variants"])),
        )

        save_result_payload(
            sent_result_message.chat.id,
            sent_result_message.message_id,
            user_id,
            user_text,
            effective_user_text,
            dialogue_context,
            tone_key,
            goal_key,
            scenario_key,
            variants_count,
            result,
        )

        add_to_history(user_id, "Пользователь", user_text)
        add_to_history(user_id, "Бот", result["best_variant_text"])
        register_user_event(user_id, "generation")

    except Exception as e:
        print(f"Ошибка генерации: {e}")
        await message.answer(
            "Не получилось собрать варианты. Попробуй ещё раз."
        )


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
    await send_start_screen(message)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await send_help_screen(message)


@dp.message(Command("reply"))
async def cmd_reply(message: Message):
    await send_quick_hub(message, message.from_user.id)


@dp.message(Command("scenario"))
async def cmd_scenario(message: Message):
    await send_scenarios_hub(message, message.from_user.id)


@dp.message(Command("save_preset"))
async def cmd_save_preset(message: Message):
    user_id = message.from_user.id
    state = get_user_module1_state(user_id)
    scenario_key = get_user_scenario(user_id)

    save_user_preset(
        user_id,
        {
            "tone": state["tone"],
            "goal": state["goal"],
            "variants_count": state["variants_count"],
            "scenario": scenario_key,
        },
    )

    await message.answer(
        "Готово — пресет сохранён.\n\n"
        f"{build_status_text(user_id)}"
    )


@dp.message(Command("my_preset"))
async def cmd_my_preset(message: Message):
    user_id = message.from_user.id

    if not apply_saved_preset_if_exists(user_id):
        await message.answer(
            "Сохранённого пресета пока нет.\n\n"
            "Сначала настрой бота и нажми /save_preset."
        )
        return

    await message.answer(
        "Твой сохранённый пресет загружен.\n\n"
        f"{build_status_text(user_id)}"
    )


@dp.message(Command("saved"))
async def cmd_saved(message: Message):
    replies = get_saved_replies(message.from_user.id)
    await message.answer(format_saved_replies_text(replies))


@dp.message(Command("coach"))
async def cmd_coach(message: Message):
    user_id = message.from_user.id
    register_user_event(user_id, "coach")
    await message.answer(build_daily_coach_text(user_id))


@dp.message(Command("progress"))
async def cmd_progress(message: Message):
    await message.answer(build_progress_text(message.from_user.id))


@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("Я на связи.")


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

    user_id = message.from_user.id
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Сейчас дам один базовый вариант...")

    try:
        reply_text = await asyncio.to_thread(
            generate_baseline_reply,
            source_text,
            dialogue_context,
        )

        await message.answer(f"Базовый вариант:\n\n{reply_text}")

        add_to_history(user_id, "Пользователь", source_text)
        add_to_history(user_id, "Бот", reply_text)

    except Exception as e:
        print(f"Ошибка base: {e}")
        await message.answer(
            "Не получилось получить базовый ответ. Попробуй ещё раз."
        )


@dp.message(Command("analyze"))
async def cmd_analyze(message: Message):
    source_text = extract_command_payload_or_reply_text(message)

    if not source_text:
        await send_analysis_hub(message, message.from_user.id)
        return

    set_user_flow_mode(message.from_user.id, FLOW_ANALYZE_MESSAGE)
    await run_message_analysis_and_send(
        message,
        source_text,
        message.from_user.id,
    )


@dp.message(Command("dialog"))
async def cmd_dialog(message: Message):
    dialog_text = extract_command_payload_or_reply_text(message)

    if not dialog_text:
        await send_analysis_hub(message, message.from_user.id)
        return

    set_user_flow_mode(message.from_user.id, FLOW_ANALYZE_DIALOG)
    await run_dialog_analysis_and_send(
        message,
        dialog_text,
        message.from_user.id,
    )


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    user_dialogues[message.from_user.id] = []
    await message.answer("Контекст очищен.")


@dp.message(F.text == "⚡ Быстрый ответ")
async def menu_quick(message: Message):
    await send_quick_hub(message, message.from_user.id)


@dp.message(F.text == "🔍 Анализ")
async def menu_analysis(message: Message):
    await send_analysis_hub(message, message.from_user.id)


@dp.message(F.text == "🎭 Сценарии")
async def menu_scenarios(message: Message):
    await send_scenarios_hub(message, message.from_user.id)


@dp.message(F.text == "💾 Память")
async def menu_memory(message: Message):
    await send_memory_hub(message, message.from_user.id)


@dp.message(F.text == "⚙️ Настройки")
async def menu_settings(message: Message):
    await send_settings_hub(message, message.from_user.id)


@dp.message(F.text == "🧠 Личный кабинет")
async def menu_locker(message: Message):
    await send_locker_hub(message, message.from_user.id)


@dp.message(F.text == "❓ Помощь")
async def menu_help(message: Message):
    await send_help_screen(message)


@dp.callback_query(F.data == "nav:main")
async def cb_nav_main(callback: CallbackQuery):
    await callback.answer()
    set_user_flow_mode(callback.from_user.id, FLOW_QUICK)
    await send_main_menu_hint(callback, callback.from_user.id)


@dp.callback_query(F.data == "hub:quick")
async def cb_hub_quick(callback: CallbackQuery):
    await callback.answer()
    set_user_flow_mode(callback.from_user.id, FLOW_QUICK)
    if callback.message:
        await callback.message.answer(
            "⚡ Быстрый ответ активен.\n\n"
            "Просто пришли текст — я соберу варианты.",
            reply_markup=build_quick_hub_keyboard(),
        )


@dp.callback_query(F.data == "hub:analysis")
async def cb_hub_analysis(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "🔍 Анализ\n\n"
            "Выбери, что хочешь разобрать.",
            reply_markup=build_analysis_hub_keyboard(),
        )


@dp.callback_query(F.data == "hub:settings")
async def cb_hub_settings(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "⚙️ Настройки\n\n"
            "Выбери, что хочешь поменять.",
            reply_markup=build_settings_hub_keyboard(),
        )
        await callback.message.answer(build_status_text(callback.from_user.id))


@dp.callback_query(F.data == "flow:quick")
async def cb_flow_quick(callback: CallbackQuery):
    await callback.answer("Жду текст")
    set_user_flow_mode(callback.from_user.id, FLOW_QUICK)
    if callback.message:
        await callback.message.answer(
            "Пришли сообщение или опиши ситуацию — соберу сильные варианты."
        )


@dp.callback_query(F.data == "flow:an_message")
async def cb_flow_an_message(callback: CallbackQuery):
    await callback.answer("Жду сообщение")
    set_user_flow_mode(callback.from_user.id, FLOW_ANALYZE_MESSAGE)
    if callback.message:
        await callback.message.answer(
            "Пришли одно сообщение, и я разберу, что в нём читается."
        )


@dp.callback_query(F.data == "flow:an_dialog")
async def cb_flow_an_dialog(callback: CallbackQuery):
    await callback.answer("Жду переписку")
    set_user_flow_mode(callback.from_user.id, FLOW_ANALYZE_DIALOG)
    if callback.message:
        await callback.message.answer(
            "Пришли переписку целиком.\n\n"
            "Лучше в формате:\n"
            "Я: ...\n"
            "Он/Она: ..."
        )


@dp.callback_query(F.data == "open:analysis_modes")
async def cb_open_analysis_modes(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери режим анализа сообщения:",
            reply_markup=build_analysis_mode_keyboard(callback.from_user.id),
        )


@dp.callback_query(F.data == "open:dialog_modes")
async def cb_open_dialog_modes(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери режим анализа переписки:",
            reply_markup=build_dialog_mode_keyboard(callback.from_user.id),
        )


@dp.callback_query(F.data == "set:tones")
async def cb_set_tones(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери тон:",
            reply_markup=build_tone_keyboard(callback.from_user.id),
        )


@dp.callback_query(F.data == "set:goals")
async def cb_set_goals(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери цель:",
            reply_markup=build_goal_keyboard(callback.from_user.id),
        )


@dp.callback_query(F.data == "set:variants")
async def cb_set_variants(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Сколько вариантов показывать?",
            reply_markup=build_variants_keyboard(callback.from_user.id),
        )


@dp.callback_query(F.data == "set:scenarios")
async def cb_set_scenarios(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери категорию сценариев:",
            reply_markup=build_scenario_groups_keyboard(),
        )


@dp.callback_query(F.data.startswith("sc_group:"))
async def cb_scenario_group(callback: CallbackQuery):
    if not callback.data:
        return

    group_key = callback.data.split(":", 1)[1]

    if group_key not in SCENARIO_GROUPS:
        await callback.answer("Категория не найдена")
        return

    await callback.answer()

    if callback.message:
        await callback.message.answer(
            f"{SCENARIO_GROUPS[group_key]['label']}\n\n"
            "Выбери сценарий:",
            reply_markup=build_scenario_items_keyboard(group_key, callback.from_user.id),
        )


@dp.callback_query(F.data.startswith("an_mode:"))
async def cb_analysis_mode(callback: CallbackQuery):
    if not callback.data:
        return

    mode = callback.data.split(":", 1)[1]

    if mode not in ANALYSIS_MODE_LABELS:
        await callback.answer("Неизвестный режим")
        return

    user_analysis_modes[callback.from_user.id] = mode
    await callback.answer("Режим сохранён")

    if callback.message:
        await callback.message.answer(build_analysis_status_text(callback.from_user.id))


@dp.callback_query(F.data.startswith("dlg_mode:"))
async def cb_dialog_mode(callback: CallbackQuery):
    if not callback.data:
        return

    mode = callback.data.split(":", 1)[1]

    if mode not in DIALOG_ANALYSIS_MODE_LABELS:
        await callback.answer("Неизвестный режим")
        return

    user_dialog_analysis_modes[callback.from_user.id] = mode
    await callback.answer("Режим сохранён")

    if callback.message:
        await callback.message.answer(build_dialog_analysis_status_text(callback.from_user.id))


@dp.callback_query(F.data.startswith("m1_tone:"))
async def cb_tone(callback: CallbackQuery):
    if not callback.data:
        return

    raw_tone = callback.data.split(":", 1)[1]
    state = get_user_module1_state(callback.from_user.id)

    if raw_tone == "neutral":
        state["tone"] = DEFAULT_TONE
    elif raw_tone in TONE_OPTIONS:
        state["tone"] = raw_tone
    else:
        await callback.answer("Неизвестный тон")
        return

    await callback.answer("Тон обновлён")

    if callback.message:
        await callback.message.answer(build_status_text(callback.from_user.id))


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

    await callback.answer("Цель обновлена")

    if callback.message:
        await callback.message.answer(build_status_text(callback.from_user.id))


@dp.callback_query(F.data.startswith("m1_variants:"))
async def cb_variants(callback: CallbackQuery):
    if not callback.data:
        return

    raw_value = callback.data.split(":", 1)[1]
    state = get_user_module1_state(callback.from_user.id)
    state["variants_count"] = normalize_variants_count(raw_value)

    await callback.answer("Количество обновлено")

    if callback.message:
        await callback.message.answer(build_status_text(callback.from_user.id))


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

    if callback.message:
        await callback.message.answer(
            f"Сценарий: {get_scenario_label(scenario_key)}\n\n"
            f"{build_status_text(user_id)}\n\n"
            f"{build_scenario_hint_text(user_id)}"
        )


@dp.callback_query(F.data == "settings:reset_history")
async def cb_reset_history(callback: CallbackQuery):
    user_dialogues[callback.from_user.id] = []
    await callback.answer("Контекст очищен")

    if callback.message:
        await callback.message.answer("Готово. Внутренний контекст переписки очищен.")


@dp.callback_query(F.data == "memory:saved")
async def cb_memory_saved(callback: CallbackQuery):
    await callback.answer()
    replies = get_saved_replies(callback.from_user.id)

    if callback.message:
        await callback.message.answer(format_saved_replies_text(replies))


@dp.callback_query(F.data == "memory:my_preset")
async def cb_memory_my_preset(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if not apply_saved_preset_if_exists(user_id):
        if callback.message:
            await callback.message.answer(
                "Сохранённого пресета пока нет."
            )
        return

    if callback.message:
        await callback.message.answer(
            "Твой сохранённый пресет загружен.\n\n"
            f"{build_status_text(user_id)}"
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

    if callback.message:
        await callback.message.answer(
            "Пресет сохранён.\n\n"
            f"{build_status_text(user_id)}"
        )


@dp.callback_query(F.data == "memory:coach")
async def cb_memory_coach(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    register_user_event(user_id, "coach")

    if callback.message:
        await callback.message.answer(build_daily_coach_text(user_id))


@dp.callback_query(F.data == "memory:progress")
async def cb_memory_progress(callback: CallbackQuery):
    await callback.answer()

    if callback.message:
        await callback.message.answer(build_progress_text(callback.from_user.id))


@dp.callback_query(F.data == "m1_regen")
async def cb_regen(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Не удалось обновить")
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Старый результат уже недоступен")
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

        new_text = format_module1_result(new_result)
        new_keyboard = build_result_keyboard(len(new_result["variants"]))

        try:
            await callback.message.edit_text(
                new_text,
                reply_markup=new_keyboard,
            )
            target_chat_id = callback.message.chat.id
            target_message_id = callback.message.message_id
        except Exception:
            new_message = await callback.message.answer(
                new_text,
                reply_markup=new_keyboard,
            )
            target_chat_id = new_message.chat.id
            target_message_id = new_message.message_id

        save_result_payload(
            target_chat_id,
            target_message_id,
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


@dp.callback_query(F.data == "m1_pick_best")
async def cb_pick_best(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    await callback.answer("Готово")
    await callback.message.answer(payload["best_variant_text"])


@dp.callback_query(F.data == "m1_save_best")
async def cb_save_best(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    total = save_reply_to_memory(
        callback.from_user.id,
        payload["best_variant_text"],
    )

    if total == 0:
        await callback.answer("Не удалось сохранить")
        return

    register_user_event(callback.from_user.id, "save")
    await callback.answer("Сохранено")

    if callback.message:
        await callback.message.answer(
            f"Сохранил. Теперь в памяти {total} ответ(ов)."
        )


@dp.callback_query(F.data == "result_tools:open")
async def cb_result_tools_open(callback: CallbackQuery):
    if not callback.message:
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    await callback.answer()

    if callback.message:
        await callback.message.answer(
            "Что проверить у лучшего варианта?",
            reply_markup=build_result_tools_keyboard(),
        )


@dp.callback_query(F.data.startswith("result_tool:"))
async def cb_result_tool(callback: CallbackQuery):
    if not callback.message or not callback.data:
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Результат уже недоступен")
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
        await callback.answer("Режим не найден")
        return

    await callback.answer("Смотрю...")

    try:
        analysis_text = await asyncio.to_thread(
            analyze_single_message_v2,
            payload["best_variant_text"],
            mode_map[tool_key],
            payload["dialogue_context"],
        )

        titles = {
            "before_send": "Проверка перед отправкой",
            "risk": "Детектор риска",
            "reaction": "Прогноз реакции",
        }

        await callback.message.answer(
            f"{titles[tool_key]}:\n\n{analysis_text}",
            reply_markup=build_result_tools_keyboard(),
        )

    except Exception as e:
        print(f"Ошибка result_tool: {e}")
        await callback.message.answer("Не получилось проверить этот вариант.")


@dp.callback_query(F.data.startswith("m1_pick:"))
async def cb_pick_variant(callback: CallbackQuery):
    if not callback.message or not callback.data:
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Результат уже недоступен")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для тебя")
        return

    raw_index = callback.data.split(":", 1)[1]

    try:
        picked_index = int(raw_index)
    except ValueError:
        await callback.answer("Неверный номер")
        return

    variants = payload["variants"]

    if picked_index < 1 or picked_index > len(variants):
        await callback.answer("Вариант не найден")
        return

    await callback.answer("Готово")
    await callback.message.answer(variants[picked_index - 1])


@dp.callback_query(F.data == "m1_close_result")
async def cb_close_result(callback: CallbackQuery):
    await callback.answer("Скрыто")
    await safe_remove_result_markup(callback)


@dp.message(F.text.startswith("/"))
async def unknown_command(message: Message):
    await message.answer(
        "Не знаю такую команду.\n\n"
        "Нажми кнопку снизу или используй /help."
    )


@dp.message(F.text)
async def handle_text_message(message: Message):
    user_text = (message.text or "").strip()

    if not user_text:
        await message.answer("Пришли текст.")
        return

    user_id = message.from_user.id
    flow_mode = get_user_flow_mode(user_id)

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