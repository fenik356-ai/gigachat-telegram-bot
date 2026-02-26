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

from gigachat_api import generate_reply_options_v2
from module1_reply_presets import (
    DEFAULT_GOAL,
    DEFAULT_TONE,
    DEFAULT_VARIANTS,
    GOAL_OPTIONS,
    TONE_OPTIONS,
    get_default_module1_state,
    get_goal_label,
    get_tone_label,
    normalize_variants_count,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("В файле .env не найден BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Память диалога
user_dialogues = {}

# Настройки Модуля 1 для каждого пользователя
user_module1_settings = {}

MAX_HISTORY_LINES = 6


def get_user_module1_state(user_id: int) -> dict:
    if user_id not in user_module1_settings:
        user_module1_settings[user_id] = get_default_module1_state()
    return user_module1_settings[user_id]


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
                InlineKeyboardButton(
                    text=variants_text(3),
                    callback_data="m1_variants:3",
                ),
                InlineKeyboardButton(
                    text=variants_text(4),
                    callback_data="m1_variants:4",
                ),
                InlineKeyboardButton(
                    text=variants_text(5),
                    callback_data="m1_variants:5",
                ),
                InlineKeyboardButton(
                    text=variants_text(6),
                    callback_data="m1_variants:6",
                ),
                InlineKeyboardButton(
                    text=variants_text(7),
                    callback_data="m1_variants:7",
                ),
            ],
        ]
    )


def build_status_text(user_id: int) -> str:
    state = get_user_module1_state(user_id)
    tone_key = state["tone"]
    goal_key = state["goal"]
    variants_count = state["variants_count"]

    tone_label = "Обычный" if tone_key == DEFAULT_TONE else get_tone_label(tone_key)

    return (
        "Текущие настройки:\n"
        f"• Тон: {tone_label}\n"
        f"• Цель: {get_goal_label(goal_key)}\n"
        f"• Вариантов: {variants_count}"
    )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user_dialogues[user_id] = []
    user_module1_settings[user_id] = get_default_module1_state()

    await message.answer(
        "Привет! Это Модуль 1: Мгновенный ответ 2.0.\n\n"
        "Что умеет бот сейчас:\n"
        "• генерирует 3–7 вариантов ответа\n"
        "• меняет тон ответа кнопками\n"
        "• меняет цель ответа кнопками\n"
        "• показывает, какой вариант сильнее и почему\n\n"
        "Выбери настройки кнопками ниже, потом отправь сообщение.",
        reply_markup=build_module1_keyboard(user_id),
    )

    await message.answer(build_status_text(user_id))


@dp.message(Command("help"))
async def cmd_help(message: Message):
    user_id = message.from_user.id
    get_user_module1_state(user_id)

    await message.answer(
        "Как пользоваться модулем:\n\n"
        "1. Нажми кнопки тона\n"
        "2. Нажми кнопку цели\n"
        "3. Выбери количество вариантов (3–7)\n"
        "4. Отправь сообщение\n"
        "5. Получи варианты + объяснение сильного варианта\n\n"
        "Команды:\n"
        "/reset — очистить память диалога",
        reply_markup=build_module1_keyboard(user_id),
    )

    await message.answer(build_status_text(user_id))


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    user_id = message.from_user.id
    user_dialogues[user_id] = []
    await message.answer("Готово. Память диалога очищена.")


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

    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=build_module1_keyboard(user_id)
        )
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

    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=build_module1_keyboard(user_id)
        )
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

    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=build_module1_keyboard(user_id)
        )
        await callback.message.answer(build_status_text(user_id))


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

    tone_key = state["tone"]
    goal_key = state["goal"]
    variants_count = state["variants_count"]
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Генерирую варианты...")

    try:
        result = await asyncio.to_thread(
            generate_reply_options_v2,
            user_text,
            variants_count,
            tone_key,
            goal_key,
            dialogue_context,
        )

        variants_text = result["formatted_variants"]
        best_index = result["best_index"]
        best_reason = result["best_reason"]

        final_text = (
            f"{variants_text}\n\n"
            f"Сильнее выглядит вариант {best_index}.\n"
            f"Почему: {best_reason}"
        )

        await message.answer(final_text)

        add_to_history(user_id, "Пользователь", user_text)

        best_variant_text = result["variants"][best_index - 1]
        add_to_history(user_id, "Бот", best_variant_text)

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