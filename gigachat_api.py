import os
import re

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


def _clean_variant(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^\s*(\d+[\).\-\:]\s*|[-•—]\s*)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_variants(raw_text: str, variants_count: int) -> list[str]:
    # 1) Главный сценарий: модель вернула "вариант1 ||| вариант2 ||| вариант3"
    parts = [p.strip() for p in raw_text.split("|||")]
    parts = [_clean_variant(p) for p in parts if p.strip()]

    # 2) Если разделитель не сработал, пробуем вытащить нумерованные пункты
    if len(parts) < 2:
        numbered_parts = re.split(r"\n?\s*(?=\d+[\).\-\:]\s)", raw_text)
        numbered_parts = [_clean_variant(p) for p in numbered_parts if _clean_variant(p)]
        if len(numbered_parts) >= 2:
            parts = numbered_parts

    # 3) Если всё ещё один кусок, пробуем разбить по строкам
    if len(parts) < 2:
        line_parts = [_clean_variant(line) for line in raw_text.splitlines() if _clean_variant(line)]
        if len(line_parts) >= 2:
            parts = line_parts

    # 4) Убираем дубли, сохраняя порядок
    unique_parts = []
    seen = set()
    for part in parts:
        key = part.lower()
        if key not in seen:
            seen.add(key)
            unique_parts.append(part)

    # 5) Если модель всё равно вернула только один вариант — оставляем его как есть
    if not unique_parts:
        unique_parts = [_clean_variant(raw_text) or "Не удалось получить корректный ответ."]

    return unique_parts[:variants_count]


def _format_numbered_list(variants: list[str]) -> str:
    lines = []
    for index, variant in enumerate(variants, start=1):
        lines.append(f"{index}) {variant}")
    return "\n".join(lines)


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
        "Каждый вариант должен быть естественным, полезным и уместным по контексту. "
        "Верни только готовые варианты без пояснений. "
        "Не используй нумерацию. "
        "Раздели варианты строго строкой с тремя вертикальными чертами: ||| \n\n"
        f"{context_block}"
        f"Новое сообщение пользователя: {user_text}"
    )

    with GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=False,
    ) as giga:
        response = giga.chat(prompt)
        raw_text = response.choices[0].message.content

    variants = _extract_variants(raw_text, variants_count)
    return _format_numbered_list(variants)
