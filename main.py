import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
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

# ключ = (chat_id, message_id)
result_message_payloads = {}

MAX_HISTORY_LINES = 6
MAX_SAVED_RESULTS = 200

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


def apply_tone_to_state(state: dict, tone_value: str):
    if tone_value == "neutral":
        state["tone"] = DEFAULT_TONE
        return

    if tone_value in TONE_OPTIONS:
        state["tone"] = tone_value


def apply_saved_preset_if_exists(user_id: int):
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
    clean_text = " ".join(text.split())

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


def build_module1_keyboard(user_id: int) -> InlineKeyboardMarkup:
    state = get_user_module1_state(user_id)

    current_tone = state["tone"]
    current_goal = state["goal"]
    current_variants = state["variants_count"]

    def tone_text(key: str, label: str) -> str:
        return f"✅ {label}" if current_tone == key else label

    def goal_text(key: str, label: str) -> str:
        return f"✅ {label}" if current_goal == key else label

    def variants_text(count: int) -> str:
        return f"✅ {count}" if current_variants == count else str(count)

    return InlineKeyboardMarkup(
        inline_keyboard=[
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
                ),
            ],
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
                InlineKeyboardButton(text=variants_text(3), callback_data="m1_variants:3"),
                InlineKeyboardButton(text=variants_text(4), callback_data="m1_variants:4"),
                InlineKeyboardButton(text=variants_text(5), callback_data="m1_variants:5"),
                InlineKeyboardButton(text=variants_text(6), callback_data="m1_variants:6"),
                InlineKeyboardButton(text=variants_text(7), callback_data="m1_variants:7"),
            ],
        ]
    )


def build_analysis_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current_mode = get_user_analysis_mode(user_id)

    def mode_text(key: str) -> str:
        label = ANALYSIS_MODE_LABELS[key]
        return f"✅ {label}" if current_mode == key else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=mode_text("general"),
                    callback_data="an_mode:general",
                ),
                InlineKeyboardButton(
                    text=mode_text("meaning"),
                    callback_data="an_mode:meaning",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=mode_text("risk"),
                    callback_data="an_mode:risk",
                ),
                InlineKeyboardButton(
                    text=mode_text("before_send"),
                    callback_data="an_mode:before_send",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=mode_text("reaction"),
                    callback_data="an_mode:reaction",
                ),
            ],
        ]
    )


def build_dialog_analysis_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current_mode = get_user_dialog_analysis_mode(user_id)

    def mode_text(key: str) -> str:
        label = DIALOG_ANALYSIS_MODE_LABELS[key]
        return f"✅ {label}" if current_mode == key else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=mode_text("general"),
                    callback_data="dlg_mode:general",
                ),
                InlineKeyboardButton(
                    text=mode_text("dynamics"),
                    callback_data="dlg_mode:dynamics",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=mode_text("interest"),
                    callback_data="dlg_mode:interest",
                ),
                InlineKeyboardButton(
                    text=mode_text("mistakes"),
                    callback_data="dlg_mode:mistakes",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=mode_text("next_step"),
                    callback_data="dlg_mode:next_step",
                ),
            ],
        ]
    )


def build_scenario_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current_scenario = get_user_scenario(user_id)

    def scenario_text(key: str) -> str:
        label = get_scenario_label(key)
        return f"✅ {label}" if current_scenario == key else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=scenario_text("neutral"),
                    callback_data="sc_mode:neutral",
                ),
                InlineKeyboardButton(
                    text=scenario_text("dating_intro"),
                    callback_data="sc_mode:dating_intro",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=scenario_text("restore_contact"),
                    callback_data="sc_mode:restore_contact",
                ),
                InlineKeyboardButton(
                    text=scenario_text("business"),
                    callback_data="sc_mode:business",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=scenario_text("sales"),
                    callback_data="sc_mode:sales",
                ),
                InlineKeyboardButton(
                    text=scenario_text("support"),
                    callback_data="sc_mode:support",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=scenario_text("soft_decline"),
                    callback_data="sc_mode:soft_decline",
                ),
                InlineKeyboardButton(
                    text=scenario_text("boundaries"),
                    callback_data="sc_mode:boundaries",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=scenario_text("hard_talk"),
                    callback_data="sc_mode:hard_talk",
                ),
                InlineKeyboardButton(
                    text=scenario_text("rescue_chat"),
                    callback_data="sc_mode:rescue_chat",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=scenario_text("first_message"),
                    callback_data="sc_mode:first_message",
                ),
                InlineKeyboardButton(
                    text=scenario_text("close_result"),
                    callback_data="sc_mode:close_result",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=scenario_text("difficult_person"),
                    callback_data="sc_mode:difficult_person",
                ),
            ],
        ]
    )


def build_result_keyboard(variants_count: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="🔁 Перегенерировать",
                callback_data="m1_regen",
            ),
            InlineKeyboardButton(
                text="✅ Взять лучший",
                callback_data="m1_pick_best",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⭐ Сохранить лучший",
                callback_data="m1_save_best",
            ),
        ],
    ]

    pick_buttons = [
        InlineKeyboardButton(
            text=f"Взять {index}",
            callback_data=f"m1_pick:{index}",
        )
        for index in range(1, variants_count + 1)
    ]

    for i in range(0, len(pick_buttons), 3):
        rows.append(pick_buttons[i:i + 3])

    rows.append(
        [
            InlineKeyboardButton(
                text="🧹 Убрать кнопки",
                callback_data="m1_close_result",
            )
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
        "Текущие настройки:\n"
        f"• Тон: {tone_label}\n"
        f"• Цель: {get_goal_label(goal_key)}\n"
        f"• Вариантов: {variants_count}\n"
        f"• Сценарий: {get_scenario_label(scenario_key)}"
    )


def build_scenario_hint_text(user_id: int) -> str:
    scenario_key = get_user_scenario(user_id)
    return (
        "Быстрый старт по сценарию:\n"
        f"• {get_scenario_starter_hint(scenario_key)}"
    )


def build_analysis_status_text(user_id: int) -> str:
    mode = get_user_analysis_mode(user_id)
    mode_label = ANALYSIS_MODE_LABELS.get(mode, "Общий")

    return (
        "Текущий режим анализа сообщения:\n"
        f"• {mode_label}"
    )


def build_dialog_analysis_status_text(user_id: int) -> str:
    mode = get_user_dialog_analysis_mode(user_id)
    mode_label = DIALOG_ANALYSIS_MODE_LABELS.get(mode, "Общий")

    return (
        "Текущий режим анализа переписки:\n"
        f"• {mode_label}"
    )


def build_progress_text(user_id: int) -> str:
    stats = get_user_engagement_stats(user_id)

    achievement_lines = ["• Пока достижений мало — просто продолжай пользоваться ботом."]
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
        f"• Сохранённых лучших ответов: {stats['saved_replies_count']}\n"
        f"• Открытий AI-коуча: {stats['coach_view_count']}\n\n"
        "Достижения:\n"
        + "\n".join(achievement_lines)
    )


def build_coach_focus(stats: dict) -> str:
    if stats["generation_count"] < 5:
        return "Сделай сегодня 3 генерации на реальных сообщениях и сравни, какой вариант сильнее."
    if stats["saved_replies_count"] < 3:
        return "Сохрани хотя бы 1 сильный ответ через кнопку ⭐ Сохранить лучший."
    if stats["analysis_count"] + stats["dialog_count"] < 5:
        return "Разбери минимум 1 входящее через /analyze или 1 диалог через /dialog."
    if stats["current_streak"] < 3:
        return "Зайди завтра снова и удержи серию активности."
    return "Прогони сегодня один реальный кейс от анализа до финального ответа и сохрани лучший результат."


def build_coach_tip(user_id: int) -> str:
    scenario_key = get_user_scenario(user_id)

    tips = {
        "neutral": "Сначала формулируй ситуацию одной короткой фразой — так ответы будут точнее.",
        "dating_intro": "В знакомствах сильнее работают лёгкие фразы, на которые легко ответить.",
        "restore_contact": "После паузы лучше не оправдываться слишком долго — мягкий вход работает лучше.",
        "business": "В деловой переписке ясность важнее креатива: один запрос — один следующий шаг.",
        "sales": "В продажах лучше снижать трение: меньше давления, больше ясной пользы.",
        "support": "В клиентском сервисе сначала снижай напряжение, потом веди к решению.",
        "soft_decline": "Мягкий отказ лучше работает, когда он короткий, ясный и без лишних оправданий.",
        "boundaries": "Границы звучат сильнее, когда ты говоришь спокойно и без агрессии.",
        "hard_talk": "В сложном разговоре лучше замедлиться и убрать лишние эмоции из формулировки.",
        "rescue_chat": "Чтобы оживить диалог, лучше вернуть лёгкость, а не пытаться резко “дожать”.",
        "first_message": "Первое сообщение должно быть простым для ответа — без перегруза и давления.",
        "close_result": "Чтобы закрыть на результат, формулируй один конкретный следующий шаг.",
        "difficult_person": "Со сложным человеком сильнее работает короткий, спокойный и предсказуемый ответ.",
    }

    return tips.get(scenario_key, tips["neutral"])


def build_daily_coach_text(user_id: int) -> str:
    stats = get_user_engagement_stats(user_id)
    scenario_label = get_scenario_label(get_user_scenario(user_id))
    saved_replies = get_saved_replies(user_id)

    if saved_replies:
        answer_of_day = saved_replies[0]
    else:
        answer_of_day = "Пока нет сохранённого ответа дня. Сначала сгенерируй варианты и нажми ⭐ Сохранить лучший."

    return (
        "Твой AI-коуч на сегодня:\n"
        f"• Текущая серия: {stats['current_streak']}\n"
        f"• Активных дней: {stats['total_active_days']}\n"
        f"• Текущий сценарий: {scenario_label}\n\n"
        f"Фокус на сегодня:\n• {build_coach_focus(stats)}\n\n"
        f"Мини-обучение:\n• {build_coach_tip(user_id)}\n\n"
        f"Ответ дня:\n• {answer_of_day}"
    )


def format_saved_replies_text(replies: list[str]) -> str:
    if not replies:
        return (
            "Сохранённые ответы пока пусты.\n\n"
            "Сначала сгенерируй варианты и нажми кнопку ⭐ Сохранить лучший."
        )

    lines = ["Сохранённые удачные ответы:"]
    for index, item in enumerate(replies, start=1):
        lines.append(f"\n{index}) {item}")

    return "\n".join(lines)


def format_module1_result(result: dict) -> str:
    variants_text = result["formatted_variants"]
    best_index = result["best_index"]
    best_reason = result["best_reason"]
    best_variant_text = result["best_variant_text"]

    return (
        "Варианты ответа:\n"
        f"{variants_text}\n\n"
        f"✅ Рекомендую вариант {best_index}:\n"
        f"{best_variant_text}\n\n"
        f"Почему он сильнее: {best_reason}"
    )


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
    key = make_result_key(chat_id, message_id)
    return result_message_payloads.get(key)


async def safe_refresh_settings_markup(callback: CallbackQuery, user_id: int):
    if not callback.message:
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_module1_keyboard(user_id)
        )
    except Exception:
        pass


async def safe_refresh_analysis_markup(callback: CallbackQuery, user_id: int):
    if not callback.message:
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_analysis_keyboard(user_id)
        )
    except Exception:
        pass


async def safe_refresh_dialog_analysis_markup(callback: CallbackQuery, user_id: int):
    if not callback.message:
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_dialog_analysis_keyboard(user_id)
        )
    except Exception:
        pass


async def safe_refresh_scenario_markup(callback: CallbackQuery, user_id: int):
    if not callback.message:
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_scenario_keyboard(user_id)
        )
    except Exception:
        pass


async def safe_remove_result_markup(callback: CallbackQuery):
    if not callback.message:
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def send_module1_panel(message: Message):
    user_id = message.from_user.id
    get_user_module1_state(user_id)
    get_user_scenario(user_id)

    await message.answer(
        "Модуль 1: Мгновенный ответ 2.0\n\n"
        "Что умеет сейчас:\n"
        "• 3–7 вариантов ответа\n"
        "• выбор тона\n"
        "• выбор цели\n"
        "• выбор сценария\n"
        "• рекомендация лучшего варианта\n"
        "• перегенерация и быстрый выбор готового текста\n"
        "• сохранение удачных ответов\n\n"
        "Выбери настройки кнопками ниже и отправь сообщение.",
        reply_markup=build_module1_keyboard(user_id),
    )

    await message.answer(build_status_text(user_id))


async def send_analysis_panel(message: Message):
    user_id = message.from_user.id
    get_user_analysis_mode(user_id)

    await message.answer(
        "Аналитика одного сообщения\n\n"
        "Доступные режимы:\n"
        "• Общий — полный разбор\n"
        "• Смысл — скрытый смысл и сигналы\n"
        "• Риск — риск, холодность, ошибки\n"
        "• Перед отправкой — как выглядит твой текст\n"
        "• Реакция — что вероятнее всего ответят\n\n"
        "Выбери режим кнопками ниже.\n"
        "Потом отправь:\n"
        "• /analyze ваш текст\n"
        "или ответь командой /analyze на сообщение.",
        reply_markup=build_analysis_keyboard(user_id),
    )

    await message.answer(build_analysis_status_text(user_id))


async def send_dialog_analysis_panel(message: Message):
    user_id = message.from_user.id
    get_user_dialog_analysis_mode(user_id)

    await message.answer(
        "Анализ всей переписки\n\n"
        "Доступные режимы:\n"
        "• Общий — полный разбор диалога\n"
        "• Динамика — кто ведёт и где просадка\n"
        "• Интерес — где упал интерес и что сработало\n"
        "• Ошибки — навязчивость, сухость, провалы\n"
        "• Следующий шаг — что делать дальше\n\n"
        "Выбери режим кнопками ниже.\n"
        "Потом отправь:\n"
        "• /dialog текст переписки\n"
        "или ответь командой /dialog на сообщение с перепиской.",
        reply_markup=build_dialog_analysis_keyboard(user_id),
    )

    await message.answer(build_dialog_analysis_status_text(user_id))


async def send_scenario_panel(message: Message):
    user_id = message.from_user.id
    get_user_scenario(user_id)

    await message.answer(
        "Режимы и сценарии\n\n"
        "Сценарий — это автопресет:\n"
        "• он сам подставляет тон\n"
        "• сам подставляет цель\n"
        "• сам подставляет количество вариантов\n\n"
        "Выбери сценарий кнопками ниже.\n"
        "После этого отправляй обычное сообщение — пресет применится автоматически.",
        reply_markup=build_scenario_keyboard(user_id),
    )

    await message.answer(build_status_text(user_id))
    await message.answer(build_scenario_hint_text(user_id))


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user_dialogues[user_id] = []
    user_module1_settings[user_id] = get_default_module1_state()
    user_analysis_modes[user_id] = "general"
    user_dialog_analysis_modes[user_id] = "general"
    user_scenarios[user_id] = DEFAULT_SCENARIO_KEY

    apply_saved_preset_if_exists(user_id)
    await send_module1_panel(message)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    user_id = message.from_user.id
    get_user_module1_state(user_id)
    get_user_analysis_mode(user_id)
    get_user_dialog_analysis_mode(user_id)
    get_user_scenario(user_id)

    await message.answer(
        "Доступные режимы:\n\n"
        "• /ping — проверить Telegram\n"
        "• /base ваш текст — один базовый ответ от GigaChat\n"
        "• /reply — открыть панель Модуля 1\n"
        "• /scenario — открыть панель сценариев\n"
        "• /save_preset — сохранить текущий личный пресет\n"
        "• /my_preset — показать текущий сохранённый пресет\n"
        "• /saved — показать сохранённые удачные ответы\n"
        "• /coach — открыть ежедневный AI-коуч\n"
        "• /progress — показать прогресс и достижения\n"
        "• /analyze — открыть панель аналитики одного сообщения\n"
        "• /analyze ваш текст — разобрать одно сообщение\n"
        "• /dialog — открыть панель анализа переписки\n"
        "• /dialog ваш_диалог — разобрать переписку целиком\n"
        "• можно ответить /analyze или /dialog на текстовое сообщение\n"
        "• обычное сообщение — Модуль 1 (варианты + лучший вариант)\n\n"
        "Под ответом Модуля 1:\n"
        "• Перегенерировать\n"
        "• Взять лучший\n"
        "• Сохранить лучший\n"
        "• Взять конкретный вариант\n"
        "• Убрать кнопки\n\n"
        "Команды:\n"
        "/reset — очистить память диалога",
        reply_markup=build_module1_keyboard(user_id),
    )

    await message.answer(build_status_text(user_id))
    await message.answer(build_scenario_hint_text(user_id))
    await message.answer(build_analysis_status_text(user_id))
    await message.answer(build_dialog_analysis_status_text(user_id))


@dp.message(Command("reply"))
async def cmd_reply_panel(message: Message):
    await send_module1_panel(message)


@dp.message(Command("scenario"))
async def cmd_scenario_panel(message: Message):
    await send_scenario_panel(message)


@dp.message(Command("save_preset"))
async def cmd_save_preset(message: Message):
    user_id = message.from_user.id
    state = get_user_module1_state(user_id)
    scenario_key = get_user_scenario(user_id)

    preset = {
        "tone": state["tone"],
        "goal": state["goal"],
        "variants_count": state["variants_count"],
        "scenario": scenario_key,
    }

    save_user_preset(user_id, preset)

    await message.answer(
        "Личный пресет сохранён.\n\n"
        f"{build_status_text(user_id)}"
    )


@dp.message(Command("my_preset"))
async def cmd_my_preset(message: Message):
    user_id = message.from_user.id
    has_preset = apply_saved_preset_if_exists(user_id)

    if not has_preset:
        await message.answer(
            "Сохранённого пресета пока нет.\n\n"
            "Сначала настрой бота и используй /save_preset."
        )
        return

    await message.answer(
        "Твой сохранённый пресет загружен.\n\n"
        f"{build_status_text(user_id)}"
    )


@dp.message(Command("saved"))
async def cmd_saved(message: Message):
    user_id = message.from_user.id
    replies = get_saved_replies(user_id)
    await message.answer(format_saved_replies_text(replies))


@dp.message(Command("coach"))
async def cmd_coach(message: Message):
    user_id = message.from_user.id
    register_user_event(user_id, "coach")
    await message.answer(build_daily_coach_text(user_id))


@dp.message(Command("progress"))
async def cmd_progress(message: Message):
    user_id = message.from_user.id
    await message.answer(build_progress_text(user_id))


@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("OK: Telegram-часть работает.")


@dp.message(Command("base"))
async def cmd_base(message: Message):
    source_text = extract_command_payload_or_reply_text(message)

    if not source_text:
        await message.answer(
            "Использование:\n"
            "/base ваш текст\n\n"
            "Или ответь командой /base на сообщение.\n\n"
            "Пример:\n"
            "/base Напиши вежливый ответ клиенту, что мы вернёмся завтра."
        )
        return

    user_id = message.from_user.id
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Проверяю базовый ответ...")

    try:
        reply_text = await asyncio.to_thread(
            generate_baseline_reply,
            source_text,
            dialogue_context,
        )

        await message.answer(f"Базовый ответ:\n\n{reply_text}")

        add_to_history(user_id, "Пользователь", source_text)
        add_to_history(user_id, "Бот", reply_text)

    except Exception as e:
        print(f"Ошибка базового режима: {e}")
        await message.answer(
            "Не удалось получить базовый ответ от GigaChat.\n"
            "Проверь ключи и попробуй ещё раз."
        )


@dp.message(Command("analyze"))
async def cmd_analyze(message: Message):
    source_text = extract_command_payload_or_reply_text(message)

    if not source_text:
        await send_analysis_panel(message)
        return

    user_id = message.from_user.id
    dialogue_context = get_dialogue_context(user_id)
    mode = get_user_analysis_mode(user_id)

    await message.answer("Анализирую сообщение...")

    try:
        analysis_text = await asyncio.to_thread(
            analyze_single_message_v2,
            source_text,
            mode,
            dialogue_context,
        )

        register_user_event(user_id, "analysis")

        await message.answer(
            f"Режим анализа: {ANALYSIS_MODE_LABELS.get(mode, 'Общий')}\n\n{analysis_text}"
        )

    except Exception as e:
        print(f"Ошибка анализа сообщения: {e}")
        await message.answer(
            "Не удалось выполнить анализ сообщения.\n"
            "Попробуй ещё раз чуть позже."
        )


@dp.message(Command("dialog"))
async def cmd_dialog(message: Message):
    dialog_text = extract_command_payload_or_reply_text(message)

    if not dialog_text:
        await send_dialog_analysis_panel(message)
        return

    user_id = message.from_user.id
    dialogue_context = get_dialogue_context(user_id)
    mode = get_user_dialog_analysis_mode(user_id)

    await message.answer("Разбираю переписку целиком...")

    try:
        analysis_text = await asyncio.to_thread(
            analyze_dialog_v2,
            dialog_text,
            mode,
            dialogue_context,
        )

        register_user_event(user_id, "dialog")

        await message.answer(
            f"Режим разбора диалога: {DIALOG_ANALYSIS_MODE_LABELS.get(mode, 'Общий')}\n\n{analysis_text}"
        )

    except Exception as e:
        print(f"Ошибка анализа переписки: {e}")
        await message.answer(
            "Не удалось выполнить анализ переписки.\n"
            "Попробуй ещё раз чуть позже."
        )


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    user_id = message.from_user.id
    user_dialogues[user_id] = []
    await message.answer("Готово. Память диалога очищена.")


@dp.callback_query(F.data.startswith("an_mode:"))
async def process_analysis_mode(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Не удалось определить режим")
        return

    mode = callback.data.split(":", 1)[1]

    if mode not in ANALYSIS_MODE_LABELS:
        await callback.answer("Неизвестный режим")
        return

    user_id = callback.from_user.id
    user_analysis_modes[user_id] = mode

    await callback.answer("Режим анализа обновлён")
    await safe_refresh_analysis_markup(callback, user_id)

    if callback.message:
        await callback.message.answer(build_analysis_status_text(user_id))


@dp.callback_query(F.data.startswith("dlg_mode:"))
async def process_dialog_analysis_mode(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Не удалось определить режим")
        return

    mode = callback.data.split(":", 1)[1]

    if mode not in DIALOG_ANALYSIS_MODE_LABELS:
        await callback.answer("Неизвестный режим")
        return

    user_id = callback.from_user.id
    user_dialog_analysis_modes[user_id] = mode

    await callback.answer("Режим разбора диалога обновлён")
    await safe_refresh_dialog_analysis_markup(callback, user_id)

    if callback.message:
        await callback.message.answer(build_dialog_analysis_status_text(user_id))


@dp.callback_query(F.data.startswith("sc_mode:"))
async def process_scenario_mode(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Не удалось определить сценарий")
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

    await callback.answer("Сценарий и автопресет применены")
    await safe_refresh_scenario_markup(callback, user_id)

    if callback.message:
        await callback.message.answer(build_status_text(user_id))
        await callback.message.answer(build_scenario_hint_text(user_id))


@dp.callback_query(F.data.startswith("m1_tone:"))
async def process_module1_tone(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Не удалось определить тон")
        return

    tone_key = callback.data.split(":", 1)[1]

    if tone_key not in TONE_OPTIONS:
        await callback.answer("Неизвестный тон")
        return

    user_id = callback.from_user.id
    state = get_user_module1_state(user_id)
    state["tone"] = tone_key

    await callback.answer("Тон обновлён")
    await safe_refresh_settings_markup(callback, user_id)

    if callback.message:
        await callback.message.answer(build_status_text(user_id))


@dp.callback_query(F.data.startswith("m1_goal:"))
async def process_module1_goal(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Не удалось определить цель")
        return

    goal_key = callback.data.split(":", 1)[1]

    if goal_key not in GOAL_OPTIONS:
        await callback.answer("Неизвестная цель")
        return

    user_id = callback.from_user.id
    state = get_user_module1_state(user_id)
    state["goal"] = goal_key

    await callback.answer("Цель обновлена")
    await safe_refresh_settings_markup(callback, user_id)

    if callback.message:
        await callback.message.answer(build_status_text(user_id))


@dp.callback_query(F.data.startswith("m1_variants:"))
async def process_module1_variants(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Не удалось определить количество")
        return

    raw_value = callback.data.split(":", 1)[1]
    variants_count = normalize_variants_count(raw_value)

    user_id = callback.from_user.id
    state = get_user_module1_state(user_id)
    state["variants_count"] = variants_count

    await callback.answer("Количество обновлено")
    await safe_refresh_settings_markup(callback, user_id)

    if callback.message:
        await callback.message.answer(build_status_text(user_id))


@dp.callback_query(F.data == "m1_regen")
async def process_module1_regen(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Не удалось обновить ответ")
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Старый ответ уже не найден")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для вас")
        return

    await callback.answer("Перегенерирую...")

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
        print(f"Ошибка перегенерации: {e}")
        await callback.message.answer(
            "Не удалось перегенерировать ответ.\n"
            "Попробуй ещё раз чуть позже."
        )


@dp.callback_query(F.data == "m1_pick_best")
async def process_module1_pick_best(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Не удалось взять лучший вариант")
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Старый ответ уже не найден")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для вас")
        return

    await callback.answer("Отправляю лучший вариант")
    await callback.message.answer(payload["best_variant_text"])


@dp.callback_query(F.data == "m1_save_best")
async def process_module1_save_best(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Не удалось сохранить")
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Старый ответ уже не найден")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для вас")
        return

    total = save_reply_to_memory(
        callback.from_user.id,
        payload["best_variant_text"],
    )

    if total == 0:
        await callback.answer("Не удалось сохранить")
        return

    register_user_event(callback.from_user.id, "save")

    await callback.answer("Лучший вариант сохранён")

    if callback.message:
        await callback.message.answer(
            f"Готово. Лучший вариант сохранён в личную память.\n\n"
            f"Сейчас сохранено: {total}"
        )


@dp.callback_query(F.data.startswith("m1_pick:"))
async def process_module1_pick(callback: CallbackQuery):
    if not callback.message or not callback.data:
        await callback.answer("Не удалось выбрать вариант")
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if not payload:
        await callback.answer("Старый ответ уже не найден")
        return

    if payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для вас")
        return

    raw_index = callback.data.split(":", 1)[1]

    try:
        picked_index = int(raw_index)
    except ValueError:
        await callback.answer("Неверный номер варианта")
        return

    variants = payload["variants"]

    if picked_index < 1 or picked_index > len(variants):
        await callback.answer("Вариант не найден")
        return

    chosen_variant = variants[picked_index - 1]

    await callback.answer("Отправляю вариант")
    await callback.message.answer(chosen_variant)


@dp.callback_query(F.data == "m1_close_result")
async def process_module1_close_result(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Не удалось убрать кнопки")
        return

    payload = get_result_payload(
        callback.message.chat.id,
        callback.message.message_id,
    )

    if payload and payload["user_id"] != callback.from_user.id:
        await callback.answer("Эта кнопка не для вас")
        return

    await callback.answer("Кнопки скрыты")
    await safe_remove_result_markup(callback)


@dp.message(F.text.startswith("/"))
async def unknown_command(message: Message):
    await message.answer("Неизвестная команда. Используй /help")


@dp.message(F.text)
async def handle_text_message(message: Message):
    user_text = message.text.strip()

    if not user_text:
        await message.answer("Пожалуйста, напиши текст.")
        return

    user_id = message.from_user.id
    state = get_user_module1_state(user_id)
    scenario_key = get_user_scenario(user_id)

    tone_key = state["tone"]
    goal_key = state["goal"]
    variants_count = state["variants_count"]
    dialogue_context = get_dialogue_context(user_id)

    effective_user_text = build_effective_scenario_text(user_text, scenario_key)

    await message.answer("Генерирую варианты...")

    try:
        result = await asyncio.to_thread(
            generate_reply_options_v2,
            effective_user_text,
            variants_count,
            tone_key,
            goal_key,
            dialogue_context,
        )

        final_text = format_module1_result(result)
        result_keyboard = build_result_keyboard(len(result["variants"]))

        sent_result_message = await message.answer(
            final_text,
            reply_markup=result_keyboard,
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
        print(f"Ошибка: {e}")
        await message.answer(
            "Не удалось получить варианты от GigaChat.\n"
            "Проверь настройки и попробуй ещё раз."
        )


async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())