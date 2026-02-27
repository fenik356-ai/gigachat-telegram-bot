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


LEGACY_STYLE_PROMPTS = {
    "friendly": "дружелюбно, тепло и просто",
    "formal": "официально, вежливо и аккуратно",
    "short": "очень коротко, по делу и понятно",
}

ANALYSIS_MODE_INSTRUCTIONS = {
    "general": "Сделай общий, сбалансированный разбор сообщения.",
    "meaning": "Сфокусируйся на скрытом смысле, настроении, сомнениях и сигналах.",
    "risk": "Сфокусируйся на рисках, напряжении, холодности и том, где можно ошибиться.",
    "before_send": "Смотри на текст как на сообщение перед отправкой: оцени, как оно читается и где риск испортить впечатление.",
    "reaction": "Сфокусируйся на вероятной реакции собеседника и лучшем следующем шаге.",
}

DIALOG_ANALYSIS_MODE_INSTRUCTIONS = {
    "general": "Сделай общий разбор диалога целиком: динамика, баланс, ошибки и лучший следующий шаг.",
    "dynamics": "Сфокусируйся на динамике разговора: кто ведёт, кто вкладывается больше, где разговор проседает.",
    "interest": "Сфокусируйся на интересе: где интерес падает, какие сообщения сработали лучше, насколько жив контакт сейчас.",
    "mistakes": "Сфокусируйся на ошибках: где есть навязчивость, сухость, давление и что пошло не так.",
    "next_step": "Сфокусируйся на текущем состоянии контакта и на самом сильном следующем шаге.",
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

    best_variant_text = variants[best_index - 1]

    return {
        "variants": variants,
        "best_index": best_index,
        "best_reason": best_reason,
        "best_variant_text": best_variant_text,
        "formatted_variants": _format_numbered_list(variants),
        "formatted_explanation": f"Почему сильнее: {best_reason}",
        "raw_text": raw_text,
    }


def _extract_labeled_block(raw_text: str, label: str, default_value: str) -> str:
    pattern = rf"{label}\s*:\s*(.*?)(?=\n[A-Z_]+\s*:|\Z)"
    match = re.search(pattern, raw_text, flags=re.IGNORECASE | re.DOTALL)

    if not match:
        return default_value

    value = match.group(1).strip()
    value = re.sub(r"\s+", " ", value).strip()

    if not value:
        return default_value

    return value


def _format_analysis_output(fields: list[tuple[str, str]]) -> str:
    lines = []

    for title, value in fields:
        lines.append(f"{title}:")
        lines.append(f"- {value}")
        lines.append("")

    return "\n".join(lines).strip()


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


def analyze_single_message_v2(
    message_text: str,
    mode: str = "general",
    dialogue_context: str = "",
) -> str:
    if not message_text or not message_text.strip():
        return "Пожалуйста, передай текст для анализа."

    if mode not in ANALYSIS_MODE_INSTRUCTIONS:
        mode = "general"

    context_block = _build_context_block(dialogue_context)
    mode_instruction = ANALYSIS_MODE_INSTRUCTIONS[mode]

    prompt = (
        "Ты сильный аналитик переписки.\n"
        "Нужно разобрать ОДНО сообщение или реплику.\n"
        f"{mode_instruction}\n\n"
        "Верни ответ СТРОГО в таком формате:\n"
        "MEANING: ...\n"
        "MOOD: ...\n"
        "SIGNALS: ...\n"
        "COLDNESS: ...\n"
        "IMAGE: ...\n"
        "RISKS: ...\n"
        "NEXT_STEP: ...\n"
        "REACTION: ...\n"
        "BEFORE_SEND: ...\n\n"
        "Правила:\n"
        "- каждый блок заполни одной короткой, практичной формулировкой\n"
        "- не добавляй вступление\n"
        "- не добавляй заключение\n"
        "- если сигнал слабый, скажи это прямо\n\n"
        f"{context_block}"
        f"Анализируемое сообщение: {message_text}"
    )

    raw_text = _call_gigachat_text(prompt)

    parsed = {
        "MEANING": _extract_labeled_block(raw_text, "MEANING", "Смысл не считывается уверенно."),
        "MOOD": _extract_labeled_block(raw_text, "MOOD", "Эмоциональный тон неочевиден."),
        "SIGNALS": _extract_labeled_block(raw_text, "SIGNALS", "Явных скрытых сигналов мало."),
        "COLDNESS": _extract_labeled_block(raw_text, "COLDNESS", "Сильной холодности не видно."),
        "IMAGE": _extract_labeled_block(raw_text, "IMAGE", "Образ со стороны выглядит нейтрально."),
        "RISKS": _extract_labeled_block(raw_text, "RISKS", "Критичных рисков не видно."),
        "NEXT_STEP": _extract_labeled_block(raw_text, "NEXT_STEP", "Лучше уточнить контекст и ответить спокойно."),
        "REACTION": _extract_labeled_block(raw_text, "REACTION", "Вероятна сдержанная реакция."),
        "BEFORE_SEND": _extract_labeled_block(raw_text, "BEFORE_SEND", "Перед отправкой стоит проверить тон и ясность."),
    }

    if mode == "meaning":
        fields = [
            ("Что, скорее всего, имеется в виду", parsed["MEANING"]),
            ("Настроение", parsed["MOOD"]),
            ("Скрытые сигналы", parsed["SIGNALS"]),
            ("Где сомнение или холодность", parsed["COLDNESS"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    elif mode == "risk":
        fields = [
            ("Риски", parsed["RISKS"]),
            ("Где сомнение или холодность", parsed["COLDNESS"]),
            ("Как это читается со стороны", parsed["IMAGE"]),
            ("Прогноз реакции", parsed["REACTION"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    elif mode == "before_send":
        fields = [
            ("Если это твой текст перед отправкой", parsed["BEFORE_SEND"]),
            ("Как это читается со стороны", parsed["IMAGE"]),
            ("Риски", parsed["RISKS"]),
            ("Прогноз реакции", parsed["REACTION"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    elif mode == "reaction":
        fields = [
            ("Настроение", parsed["MOOD"]),
            ("Прогноз реакции", parsed["REACTION"]),
            ("Скрытые сигналы", parsed["SIGNALS"]),
            ("Риски", parsed["RISKS"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    else:
        fields = [
            ("Что, скорее всего, имеется в виду", parsed["MEANING"]),
            ("Настроение", parsed["MOOD"]),
            ("Скрытые сигналы", parsed["SIGNALS"]),
            ("Где сомнение или холодность", parsed["COLDNESS"]),
            ("Как это читается со стороны", parsed["IMAGE"]),
            ("Риски", parsed["RISKS"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
            ("Прогноз реакции", parsed["REACTION"]),
            ("Если это твой текст перед отправкой", parsed["BEFORE_SEND"]),
        ]

    return _format_analysis_output(fields)


def analyze_dialog_v2(
    dialog_text: str,
    mode: str = "general",
    dialogue_context: str = "",
) -> str:
    if not dialog_text or not dialog_text.strip():
        return "Пожалуйста, передай текст переписки для анализа."

    if mode not in DIALOG_ANALYSIS_MODE_INSTRUCTIONS:
        mode = "general"

    context_block = _build_context_block(dialogue_context)
    mode_instruction = DIALOG_ANALYSIS_MODE_INSTRUCTIONS[mode]

    prompt = (
        "Ты сильный аналитик переписки.\n"
        "Нужно разобрать диалог целиком, а не одно сообщение.\n"
        f"{mode_instruction}\n\n"
        "Верни ответ СТРОГО в таком формате:\n"
        "BALANCE: ...\n"
        "LEAD: ...\n"
        "INTEREST_DROP: ...\n"
        "PUSHINESS: ...\n"
        "DRYNESS: ...\n"
        "BEST_MESSAGES: ...\n"
        "WHAT_WENT_WRONG: ...\n"
        "STATE_NOW: ...\n"
        "NEXT_STEP: ...\n\n"
        "Правила:\n"
        "- каждый блок заполни одной короткой, практичной формулировкой\n"
        "- не добавляй вступление\n"
        "- не добавляй заключение\n"
        "- если вывод слабый, так и скажи\n\n"
        f"{context_block}"
        f"Анализируемая переписка:\n{dialog_text}"
    )

    raw_text = _call_gigachat_text(prompt)

    parsed = {
        "BALANCE": _extract_labeled_block(raw_text, "BALANCE", "Баланс вклада сторон считывается неуверенно."),
        "LEAD": _extract_labeled_block(raw_text, "LEAD", "Неочевидно, кто стабильно ведёт разговор."),
        "INTEREST_DROP": _extract_labeled_block(raw_text, "INTEREST_DROP", "Явный момент падения интереса не выделяется."),
        "PUSHINESS": _extract_labeled_block(raw_text, "PUSHINESS", "Навязчивость выражена слабо или неочевидно."),
        "DRYNESS": _extract_labeled_block(raw_text, "DRYNESS", "Сильной сухости не видно или она не доминирует."),
        "BEST_MESSAGES": _extract_labeled_block(raw_text, "BEST_MESSAGES", "Самые сильные сообщения не выделяются уверенно."),
        "WHAT_WENT_WRONG": _extract_labeled_block(raw_text, "WHAT_WENT_WRONG", "Явный провал не считывается уверенно."),
        "STATE_NOW": _extract_labeled_block(raw_text, "STATE_NOW", "Текущее состояние контакта считывается неуверенно."),
        "NEXT_STEP": _extract_labeled_block(raw_text, "NEXT_STEP", "Лучше выбрать спокойный, не давящий следующий шаг."),
    }

    if mode == "dynamics":
        fields = [
            ("Кто вкладывается больше", parsed["BALANCE"]),
            ("Кто ведёт разговор", parsed["LEAD"]),
            ("Где падает интерес", parsed["INTEREST_DROP"]),
            ("Текущее состояние контакта", parsed["STATE_NOW"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    elif mode == "interest":
        fields = [
            ("Где падает интерес", parsed["INTEREST_DROP"]),
            ("Какие сообщения сработали лучше", parsed["BEST_MESSAGES"]),
            ("Текущее состояние контакта", parsed["STATE_NOW"]),
            ("Что, скорее всего, пошло не так", parsed["WHAT_WENT_WRONG"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    elif mode == "mistakes":
        fields = [
            ("Где ты выглядишь навязчиво", parsed["PUSHINESS"]),
            ("Где ты выглядишь слишком сухо", parsed["DRYNESS"]),
            ("Что, скорее всего, пошло не так", parsed["WHAT_WENT_WRONG"]),
            ("Текущее состояние контакта", parsed["STATE_NOW"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    elif mode == "next_step":
        fields = [
            ("Текущее состояние контакта", parsed["STATE_NOW"]),
            ("Где падает интерес", parsed["INTEREST_DROP"]),
            ("Что, скорее всего, пошло не так", parsed["WHAT_WENT_WRONG"]),
            ("Какие сообщения сработали лучше", parsed["BEST_MESSAGES"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    else:
        fields = [
            ("Кто вкладывается больше", parsed["BALANCE"]),
            ("Кто ведёт разговор", parsed["LEAD"]),
            ("Где падает интерес", parsed["INTEREST_DROP"]),
            ("Где ты выглядишь навязчиво", parsed["PUSHINESS"]),
            ("Где ты выглядишь слишком сухо", parsed["DRYNESS"]),
            ("Какие сообщения сработали лучше", parsed["BEST_MESSAGES"]),
            ("Что, скорее всего, пошло не так", parsed["WHAT_WENT_WRONG"]),
            ("Текущее состояние контакта", parsed["STATE_NOW"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]

    return _format_analysis_output(fields)


def analyze_dialog_v1(dialog_text: str, dialogue_context: str = "") -> str:
    return analyze_dialog_v2(dialog_text, "general", dialogue_context)


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
            "best_variant_text": fallback_text,
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
    if not user_text or not user_text.strip():
        return "Пожалуйста, напиши текстовое сообщение."

    if style not in LEGACY_STYLE_PROMPTS:
        style = "friendly"

    try:
        variants_count = int(variants_count)
    except (TypeError, ValueError):
        variants_count = 3

    variants_count = max(1, min(variants_count, 3))
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