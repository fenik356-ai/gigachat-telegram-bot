import os

from dotenv import load_dotenv
from gigachat import GigaChat

load_dotenv()

GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")

if not GIGACHAT_CREDENTIALS:
    raise ValueError("В файле .env не найден GIGACHAT_CREDENTIALS")


STYLE_PROMPTS = {
    "friendly": "дружелюбно, тепло и просто",
    "formal": "официально, вежливо и аккуратно",
    "short": "очень коротко, по делу и понятно",
}


def get_gigachat_response(
    user_text: str,
    style: str = "friendly",
    variants_count: int = 3,
    dialogue_context: str = "",
) -> str:
    if not user_text or not user_text.strip():
        return "Пожалуйста, напиши текстовое сообщение."

    if style not in STYLE_PROMPTS:
        style = "friendly"

    variants_count = max(1, min(variants_count, 3))

    answer_template = "\n".join([f"{i}) ..." for i in range(1, variants_count + 1)])

    context_block = ""
    if dialogue_context.strip():
        context_block = (
            "История последних сообщений:\n"
            f"{dialogue_context}\n\n"
            "Учитывай эту историю, но не пересказывай её.\n\n"
        )

    prompt = (
        "Ты помощник по переписке. "
        f"Сформируй {variants_count} разных варианта ответа на новое сообщение пользователя. "
        f"Пиши {STYLE_PROMPTS[style]}. "
        "Варианты должны быть полезными, естественными и уместными по контексту. "
        "Не добавляй пояснений перед списком и после списка. "
        f"Оформи строго так:\n{answer_template}\n\n"
        f"{context_block}"
        f"Новое сообщение пользователя: {user_text}"
    )

    with GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=False,  # для простой локальной/тестовой версии
    ) as giga:
        response = giga.chat(prompt)
        return response.choices[0].message.content
