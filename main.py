import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

from gigachat_api import get_gigachat_response

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("В файле .env не найден BOT_TOKEN")


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Простое хранение стиля в памяти:
# ключ = user_id, значение = friendly / formal / short
user_styles = {}


def get_style_label(style_key: str) -> str:
    labels = {
        "friendly": "дружелюбный",
        "formal": "официальный",
        "short": "короткий",
    }
    return labels.get(style_key, "дружелюбный")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_styles[message.from_user.id] = "friendly"

    await message.answer(
        "Привет! Я Telegram-бот с GigaChat.\n\n"
        "Что я умею сейчас:\n"
        "• принимаю твоё сообщение\n"
        "• отправляю его в GigaChat\n"
        "• возвращаю 3 варианта ответа\n\n"
        "Команды:\n"
        "/help — помощь\n"
        "/style_friendly — дружелюбный стиль\n"
        "/style_formal — официальный стиль\n"
        "/style_short — короткий стиль\n\n"
        "Просто напиши сообщение."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    current_style = user_styles.get(message.from_user.id, "friendly")

    await message.answer(
        "Как пользоваться ботом:\n\n"
        "1. Отправь обычное сообщение\n"
        "2. Бот отправит его в GigaChat\n"
        "3. Ты получишь 3 варианта ответа\n\n"
        f"Текущий стиль: {get_style_label(current_style)}\n\n"
        "Команды:\n"
        "/style_friendly — дружелюбный стиль\n"
        "/style_formal — официальный стиль\n"
        "/style_short — короткий стиль"
    )


@dp.message(Command("style_friendly"))
async def cmd_style_friendly(message: Message):
    user_styles[message.from_user.id] = "friendly"
    await message.answer("Готово. Теперь стиль ответов: дружелюбный.")


@dp.message(Command("style_formal"))
async def cmd_style_formal(message: Message):
    user_styles[message.from_user.id] = "formal"
    await message.answer("Готово. Теперь стиль ответов: официальный.")


@dp.message(Command("style_short"))
async def cmd_style_short(message: Message):
    user_styles[message.from_user.id] = "short"
    await message.answer("Готово. Теперь стиль ответов: короткий.")


@dp.message(F.text.startswith("/"))
async def unknown_command(message: Message):
    await message.answer("Неизвестная команда. Используй /help")


@dp.message(F.text)
async def handle_text_message(message: Message):
    user_text = message.text.strip()

    if not user_text:
        await message.answer("Пожалуйста, напиши текст.")
        return

    current_style = user_styles.get(message.from_user.id, "friendly")

    await message.answer("Думаю...")

    try:
        response_text = await asyncio.to_thread(
            get_gigachat_response,
            user_text,
            current_style,
            3,
        )
        await message.answer(response_text)
    except Exception as e:
        print(f"Ошибка: {e}")
        await message.answer(
            "Не удалось получить ответ от GigaChat.\n"
            "Проверь подключение к интернету и настройки в .env, затем попробуй ещё раз."
        )


async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())