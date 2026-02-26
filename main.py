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

from gigachat_api import get_gigachat_response

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("В файле .env не найден BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Простое хранение данных в памяти
user_styles = {}
user_dialogues = {}

MAX_HISTORY_LINES = 6


def get_style_label(style_key: str) -> str:
    labels = {
        "friendly": "дружелюбный",
        "formal": "официальный",
        "short": "короткий",
    }
    return labels.get(style_key, "дружелюбный")


def get_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="😊 Дружелюбный", callback_data="style:friendly")],
            [InlineKeyboardButton(text="🧾 Официальный", callback_data="style:formal")],
            [InlineKeyboardButton(text="⚡ Короткий", callback_data="style:short")],
        ]
    )


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


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_styles[message.from_user.id] = "friendly"
    user_dialogues[message.from_user.id] = []

    await message.answer(
        "Привет! Я Telegram-бот с GigaChat.\n\n"
        "Что я умею сейчас:\n"
        "• принимаю твоё сообщение\n"
        "• учитываю несколько последних сообщений\n"
        "• отправляю запрос в GigaChat\n"
        "• возвращаю 3 варианта ответа\n\n"
        "Нажми кнопку ниже, чтобы выбрать стиль.\n"
        "Команды:\n"
        "/help — помощь\n"
        "/reset — очистить память диалога",
        reply_markup=get_style_keyboard(),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    current_style = user_styles.get(message.from_user.id, "friendly")

    await message.answer(
        "Как пользоваться ботом:\n\n"
        "1. Выбери стиль кнопкой\n"
        "2. Отправь обычное сообщение\n"
        "3. Бот учтёт несколько последних сообщений\n"
        "4. Ты получишь 3 варианта ответа\n\n"
        f"Текущий стиль: {get_style_label(current_style)}\n\n"
        "Команды:\n"
        "/reset — очистить память диалога",
        reply_markup=get_style_keyboard(),
    )


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    user_dialogues[message.from_user.id] = []
    await message.answer("Готово. Память диалога очищена.")


@dp.callback_query(F.data.startswith("style:"))
async def process_style_button(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Не удалось определить стиль")
        return

    style_value = callback.data.split(":", 1)[1]

    if style_value not in {"friendly", "formal", "short"}:
        await callback.answer("Неизвестный стиль")
        return

    user_styles[callback.from_user.id] = style_value

    await callback.answer("Стиль обновлён")

    if callback.message:
        await callback.message.answer(
            f"Готово. Теперь стиль ответов: {get_style_label(style_value)}."
        )


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
    current_style = user_styles.get(user_id, "friendly")
    dialogue_context = get_dialogue_context(user_id)

    await message.answer("Думаю...")

    try:
        response_text = await asyncio.to_thread(
            get_gigachat_response,
            user_text,
            current_style,
            3,
            dialogue_context,
        )

        await message.answer(response_text)

        add_to_history(user_id, "Пользователь", user_text)
        add_to_history(user_id, "Бот", response_text)

    except Exception as e:
        print(f"Ошибка: {e}")
        await message.answer(
            "Не удалось получить ответ от GigaChat.\n"
            "Проверь интернет и настройки, затем попробуй ещё раз."
        )


async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
