import os
import re

from dotenv import load_dotenv
from gigachat import GigaChat

from module1_reply_presets import (
    DEFAULT_GOAL,
    DEFAULT_TONE,
    DEFAULT_VARIANTS,
    get_goal_instruction,
    get_tone_instruction,
    normalize_variants_count,
)

load_dotenv()

GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")

if not GIGACHAT_CREDENTIALS:
    raise ValueError("В файле .env не найден GIGACHAT_CREDENTIALS")


# Оставляем для совместимости со старым режимом
LEGACY_STYLE_PROMPTS = {
    "friendly": "дружелюбно, тепло и просто",
    "formal": "официально, вежливо и аккуратно",
    "short": "очень коротко, по делу и понятно",
}


def _call_gigachat_text(prompt: str) -> str:
    with GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=False,
    ) as giga:
        response = giga.chat(prompt)
        return response.choices[0].message.content


def _clean_variant(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^\s*(\d+[\).\-\:]\s*|[-•—]\s*)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_variants(raw_text: str, variants_count: int) -> list[str]:
    parts = [p.strip() for p in raw_text.split("|||")]
    parts = [_clean_variant(p) for p in parts if p.strip()]

    if len(parts) < 2:
        numbered_parts = re.split(r"\n?\s*(?=\d+[\).\-\:]\s)", raw_text)
        numbered_parts = [_clean_variant(p) for p in numbered_parts if _clean_variant(p)]
        if len(numbered_parts) >= 2:
            parts = numbered_parts

    if len(parts) < 2:
        line_parts = [_clean_variant(line) for line in raw_text.splitlines() if _clean_variant(line)]
        if len(line_parts) >= 2:
            parts = line_parts

    unique_parts = []
    seen = set()

    for part in parts:
        key = part.lower()
        if key not in seen:
            seen.add(key)
            unique_parts.append(part)

    if not unique_parts:
        fallback = _clean_variant(raw_text)
        unique_parts = [fallback or "Не удалось получить корректный ответ."]

    return unique_parts[:variants_count]


def _format_numbered_list(variants: list[str]) -> str:
    lines = []
    for index, variant in enumerate(variants, start=1):
        lines.append(f"{index}) {variant}")
    return "\n".join(lines)


def _build_context_block(dialogue_context: str) -> str:
    if not dialogue_context or not dialogue_context.strip():
        return ""

    return (
        "История последних сообщений:\n"
        f"{dialogue_context.strip()}\n\n"
        "Учитывай эту историю, но не пересказывай её.\n\n"
    )


def _parse_module1_response(raw_text: str, variants_count: int) -> dict:
    best_index = 1
    best_reason = "Этот вариант выглядит самым ясным и уместным."

    best_index_match = re.search(r"BEST_INDEX\s*[:=]\s*(\d+)", raw_text, flags=re.IGNORECASE)
    if best_index_match:
        try:
            best_index = int(best_index_match.group(1))
        except ValueError:
            best_index = 1

    best_reason_match = re.search(r"BEST_REASON\s*[:=]\s*(.+)", raw_text, flags=re.IGNORECASE)
    if best_reason_match:
        extracted_reason = best_reason_match.group(1).strip()
        if extracted_reason:
            best_reason = extracted_reason

    variants_match = re.search(r"VARIANTS\s*[:=]\s*(.+)", raw_text, flags=re.IGNORECASE | re.DOTALL)

    if variants_match:
        variants_source = variants_match.group(1).strip()
    else:
        variants_source = re.sub(
            r"^\s*BEST_INDEX\s*[:=].*$",
            "",
            raw_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        variants_source = re.sub(
            r"^\s*BEST_REASON\s*[:=].*$",
            "",
            variants_source,
            flags=re.IGNORECASE | re.MULTILINE,
        )

    variants = _extract_variants(variants_source, variants_count)

    if best_index < 1 or best_index > len(variants):
        best_index = 1

    return {
        "variants": variants,
        "best_index": best_index,
        "best_reason": best_reason,
        "formatted_variants": _format_numbered_list(variants),
        "formatted_explanation": f"Почему сильнее: {best_reason}",
        "raw_text": raw_text,
    }


def generate_baseline_reply(user_text: str, dialogue_context: str = "") -> str:
    if not user_text or not user_text.strip():
        return "Пожалуйста, напиши текстовое сообщение."

    context_block = _build_context_block(dialogue_context)

    prompt = (
        "Ты полезный помощник по переписке.\n"
        "Нужно дать один готовый, естественный и уместный ответ на сообщение пользователя.\n"
        "Верни только сам текст ответа, без пояснений, без нумерации, без вступлений.\n\n"
        f"{context_block}"
        f"Сообщение пользователя: {user_text}"
    )

    raw_text = _call_gigachat_text(prompt)
    cleaned = _clean_variant(raw_text)

    if not cleaned:
        return "Не удалось получить корректный базовый ответ."

    return cleaned


def generate_reply_options_v2(
    user_text: str,
    variants_count: int = DEFAULT_VARIANTS,
    tone_key: str = DEFAULT_TONE,
    goal_key: str = DEFAULT_GOAL,
    dialogue_context: str = "",
) -> dict:
    if not user_text or not user_text.strip():
        fallback_text = "Пожалуйста, напиши текстовое сообщение."
        return {
            "variants": [fallback_text],
            "best_index": 1,
            "best_reason": "Без входного сообщения нельзя предложить варианты.",
            "formatted_variants": f"1) {fallback_text}",
            "formatted_explanation": "Почему сильнее: сначала нужен текст сообщения.",
            "raw_text": fallback_text,
        }

    variants_count = normalize_variants_count(variants_count)
    tone_instruction = get_tone_instruction(tone_key)
    goal_instruction = get_goal_instruction(goal_key)
    context_block = _build_context_block(dialogue_context)

    prompt = (
        "Ты сильный помощник по переписке.\n"
        "Нужно предложить несколько готовых вариантов ответа на сообщение пользователя.\n"
        f"Количество вариантов: {variants_count}.\n"
        f"Требование по тону: {tone_instruction}.\n"
        f"Цель ответа: {goal_instruction}.\n\n"
        "Верни ответ СТРОГО в таком формате:\n"
        "BEST_INDEX: номер самого сильного варианта\n"
        "BEST_REASON: одна короткая причина, почему этот вариант сильнее других\n"
        "VARIANTS: вариант 1 ||| вариант 2 ||| вариант 3\n\n"
        "Правила:\n"
        "- не добавляй никаких вступлений\n"
        "- не добавляй пояснений вне указанного формата\n"
        "- каждый вариант должен быть готовым текстом, который можно сразу отправить\n"
        "- варианты должны отличаться по формулировке, а не только по одному слову\n\n"
        f"{context_block}"
        f"Сообщение пользователя: {user_text}"
    )

    raw_text = _call_gigachat_text(prompt)
    return _parse_module1_response(raw_text, variants_count)


def get_gigachat_response(
    user_text: str,
    style: str = "friendly",
    variants_count: int = 3,
    dialogue_context: str = "",
) -> str:
    """
    Старая совместимая функция.
    Оставляем её, чтобы текущий бот продолжал работать, если где-то ещё используется старый режим.
    """
    if not user_text or not user_text.strip():
        return "Пожалуйста, напиши текстовое сообщение."

    if style not in LEGACY_STYLE_PROMPTS:
        style = "friendly"

    variants_count = max(1, min(int(variants_count), 3))
    context_block = _build_context_block(dialogue_context)

    prompt = (
        "Ты помощник по переписке. "
        f"Сформируй {variants_count} разных варианта ответа на новое сообщение пользователя. "
        f"Пиши {LEGACY_STYLE_PROMPTS[style]}. "
        "Каждый вариант должен быть естественным, полезным и уместным по контексту. "
        "Верни только готовые варианты без пояснений. "
        "Не используй нумерацию. "
        "Раздели варианты строго строкой с тремя вертикальными чертами: ||| \n\n"
        f"{context_block}"
        f"Новое сообщение пользователя: {user_text}"
    )

    raw_text = _call_gigachat_text(prompt)
    variants = _extract_variants(raw_text, variants_count)
    return _format_numbered_list(variants)