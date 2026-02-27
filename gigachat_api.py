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
    "formal": "спокойно, вежливо и аккуратно",
    "short": "коротко, по делу и без лишней воды",
}

ANALYSIS_MODE_INSTRUCTIONS = {
    "general": "Сделай полный, практичный разбор.",
    "meaning": "Сфокусируйся на скрытом смысле, интересе, сомнениях и сигналах.",
    "risk": "Сфокусируйся на рисках, границах, холодности и местах, где можно ошибиться.",
    "before_send": "Смотри на текст как на сообщение перед отправкой: оцени, как он читается и где может подвести.",
    "reaction": "Сфокусируйся на вероятной реакции собеседника и лучшем следующем шаге.",
}

DIALOG_MODE_INSTRUCTIONS = {
    "general": "Сделай полный, практичный разбор диалога целиком.",
    "dynamics": "Сфокусируйся на динамике, балансе вклада и том, кто ведёт разговор.",
    "interest": "Сфокусируйся на интересе, теплоте и том, где разговор проседает.",
    "mistakes": "Сфокусируйся на ошибках: навязчивость, сухость, давление и провалы.",
    "next_step": "Сфокусируйся на текущем состоянии диалога и самом сильном следующем шаге.",
}


def _call_gigachat_text(prompt: str) -> str:
    with GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=False,
    ) as giga:
        response = giga.chat(prompt)
        return response.choices[0].message.content


def _clean_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_context_block(dialogue_context: str) -> str:
    if not dialogue_context or not dialogue_context.strip():
        return ""

    return (
        "Короткий контекст последних сообщений:\n"
        f"{dialogue_context.strip()}\n\n"
        "Учитывай контекст, но не пересказывай его.\n\n"
    )


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
        unique_parts = [fallback or "Не удалось получить корректный вариант."]

    return unique_parts[:variants_count]


def _format_numbered_list(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _extract_labeled_block(raw_text: str, label: str, default_value: str) -> str:
    pattern = rf"{label}\s*:\s*(.*?)(?=\n[A-Z_]+\s*:|\Z)"
    match = re.search(pattern, raw_text, flags=re.IGNORECASE | re.DOTALL)

    if not match:
        return default_value

    value = _clean_text(match.group(1))
    return value or default_value


def _format_sections(fields: list[tuple[str, str]]) -> str:
    lines = []

    for title, value in fields:
        lines.append(f"{title}:")
        lines.append(f"— {value}")
        lines.append("")

    return "\n".join(lines).strip()


def _parse_module1_response(raw_text: str, variants_count: int) -> dict:
    best_index = 1
    best_reason = "Он звучит естественнее и лучше двигает диалог дальше."

    best_index_match = re.search(r"BEST_INDEX\s*[:=]\s*(\d+)", raw_text, flags=re.IGNORECASE)
    if best_index_match:
        try:
            best_index = int(best_index_match.group(1))
        except ValueError:
            best_index = 1

    best_reason_match = re.search(r"BEST_REASON\s*[:=]\s*(.+)", raw_text, flags=re.IGNORECASE)
    if best_reason_match:
        extracted_reason = _clean_text(best_reason_match.group(1))
        if extracted_reason:
            best_reason = extracted_reason

    variants_match = re.search(r"VARIANTS\s*[:=]\s*(.+)", raw_text, flags=re.IGNORECASE | re.DOTALL)
    variants_source = variants_match.group(1).strip() if variants_match else raw_text
    variants = _extract_variants(variants_source, variants_count)

    if best_index < 1 or best_index > len(variants):
        best_index = 1

    return {
        "variants": variants,
        "best_index": best_index,
        "best_reason": best_reason,
        "best_variant_text": variants[best_index - 1],
        "formatted_variants": _format_numbered_list(variants),
        "raw_text": raw_text,
    }


def generate_baseline_reply(user_text: str, dialogue_context: str = "") -> str:
    if not user_text or not user_text.strip():
        return "Сначала пришли текст."

    context_block = _build_context_block(dialogue_context)

    prompt = (
        "Ты сильный помощник по переписке.\n"
        "Нужно дать ОДИН готовый ответ.\n"
        "Пиши как живой человек: естественно, коротко, без канцелярита и без лишних вступлений.\n"
        "Не пиши как бот или корпоративный ассистент.\n"
        "Верни только сам текст ответа.\n\n"
        f"{context_block}"
        f"Ситуация / сообщение:\n{user_text}"
    )

    raw_text = _call_gigachat_text(prompt)
    return _clean_text(raw_text) or "Не удалось получить корректный ответ."


def build_message_from_brief(brief_text: str, dialogue_context: str = "") -> str:
    if not brief_text or not brief_text.strip():
        return "Сначала опиши, что ты хочешь сказать."

    context_block = _build_context_block(dialogue_context)

    prompt = (
        "Ты сильный помощник по переписке.\n"
        "Нужно превратить сырую идею пользователя в одно готовое сообщение, которое можно сразу отправить.\n"
        "Пиши живо, естественно, коротко и по-человечески.\n"
        "Без канцелярита, без объяснений, без нескольких вариантов.\n"
        "Верни только сам текст сообщения.\n\n"
        f"{context_block}"
        f"Сырая идея / задача:\n{brief_text}"
    )

    raw_text = _call_gigachat_text(prompt)
    return _clean_text(raw_text) or "Не удалось собрать сообщение."


def generate_reply_options_v2(
    user_text: str,
    variants_count: int = DEFAULT_VARIANTS,
    tone_key: str = DEFAULT_TONE,
    goal_key: str = DEFAULT_GOAL,
    dialogue_context: str = "",
) -> dict:
    if not user_text or not user_text.strip():
        fallback_text = "Сначала пришли текст."
        return {
            "variants": [fallback_text],
            "best_index": 1,
            "best_reason": "Без текста нельзя собрать сильный ответ.",
            "best_variant_text": fallback_text,
            "formatted_variants": f"1. {fallback_text}",
            "raw_text": fallback_text,
        }

    variants_count = normalize_variants_count(variants_count)
    tone_instruction = get_tone_instruction(tone_key)
    goal_instruction = get_goal_instruction(goal_key)
    context_block = _build_context_block(dialogue_context)

    prompt = (
        "Ты сильный помощник по переписке.\n"
        "Твоя задача — предложить несколько готовых вариантов ответа.\n"
        "Пиши как живой человек: естественно, без канцелярита, без лишней тяжести, без странных оборотов.\n"
        "Не используй шаблонные ассистентские фразы.\n"
        "Каждый вариант должен быть готов к отправке сразу.\n"
        "Варианты должны реально отличаться, а не быть копиями.\n"
        f"Количество вариантов: {variants_count}.\n"
        f"Тон: {tone_instruction}.\n"
        f"Цель: {goal_instruction}.\n\n"
        "Верни ответ СТРОГО в таком формате:\n"
        "BEST_INDEX: номер самого сильного варианта\n"
        "BEST_REASON: коротко, почему именно он сильнее в реальном диалоге\n"
        "VARIANTS: вариант 1 ||| вариант 2 ||| вариант 3\n\n"
        f"{context_block}"
        f"Ситуация / сообщение:\n{user_text}"
    )

    raw_text = _call_gigachat_text(prompt)
    return _parse_module1_response(raw_text, variants_count)


def compare_reply_variants(variants: list[str], dialogue_context: str = "") -> str:
    clean_variants = [_clean_text(v) for v in variants if _clean_text(v)]

    if len(clean_variants) < 2:
        return "Сравнивать пока нечего — нужен хотя бы 2 варианта."

    numbered = "\n".join(f"{idx}. {text}" for idx, text in enumerate(clean_variants, start=1))
    context_block = _build_context_block(dialogue_context)

    prompt = (
        "Ты сильный редактор переписки.\n"
        "Сравни варианты ответа не по красоте, а по силе в реальном диалоге.\n"
        "Оцени: какой сильнее, какой безопаснее, какой теплее, и где главный риск.\n"
        "Пиши коротко и практично.\n\n"
        "Верни ответ СТРОГО в формате:\n"
        "WINNER: номер\n"
        "STRONGEST: ...\n"
        "SAFEST: ...\n"
        "WARMEST: ...\n"
        "RISK: ...\n\n"
        f"{context_block}"
        f"Варианты:\n{numbered}"
    )

    raw_text = _call_gigachat_text(prompt)

    winner = _extract_labeled_block(raw_text, "WINNER", "1")
    strongest = _extract_labeled_block(raw_text, "STRONGEST", "Самым сильным выглядит первый вариант.")
    safest = _extract_labeled_block(raw_text, "SAFEST", "Самый безопасный вывод считывается неуверенно.")
    warmest = _extract_labeled_block(raw_text, "WARMEST", "Самый тёплый вывод считывается неуверенно.")
    risk = _extract_labeled_block(raw_text, "RISK", "Главный риск неочевиден.")

    return (
        f"Сравнение вариантов:\n"
        f"— Сильнее всего сейчас: №{winner}\n"
        f"— Почему: {strongest}\n"
        f"— Самый безопасный: {safest}\n"
        f"— Самый тёплый: {warmest}\n"
        f"— Главный риск: {risk}"
    )


def analyze_single_message_v2(
    message_text: str,
    mode: str = "general",
    dialogue_context: str = "",
) -> str:
    if not message_text or not message_text.strip():
        return "Сначала пришли сообщение для разбора."

    if mode not in ANALYSIS_MODE_INSTRUCTIONS:
        mode = "general"

    context_block = _build_context_block(dialogue_context)
    mode_instruction = ANALYSIS_MODE_INSTRUCTIONS[mode]

    prompt = (
        "Ты сильный аналитик переписки.\n"
        "Нужно разобрать ОДНО сообщение.\n"
        f"{mode_instruction}\n"
        "Пиши коротко, по делу и без общих фраз.\n\n"
        "Верни ответ СТРОГО в формате:\n"
        "MEANING: ...\n"
        "MOOD: ...\n"
        "INTEREST: ...\n"
        "DOUBT: ...\n"
        "SIGNALS: ...\n"
        "BOUNDARY: ...\n"
        "IMAGE: ...\n"
        "RISKS: ...\n"
        "NEXT_STEP: ...\n"
        "REACTION: ...\n\n"
        f"{context_block}"
        f"Сообщение:\n{message_text}"
    )

    raw_text = _call_gigachat_text(prompt)

    parsed = {
        "MEANING": _extract_labeled_block(raw_text, "MEANING", "Смысл считывается не до конца."),
        "MOOD": _extract_labeled_block(raw_text, "MOOD", "Тон нейтральный или смешанный."),
        "INTEREST": _extract_labeled_block(raw_text, "INTEREST", "Интерес и холодность выражены неярко."),
        "DOUBT": _extract_labeled_block(raw_text, "DOUBT", "Явное сомнение выражено слабо."),
        "SIGNALS": _extract_labeled_block(raw_text, "SIGNALS", "Скрытые сигналы есть, но не слишком сильные."),
        "BOUNDARY": _extract_labeled_block(raw_text, "BOUNDARY", "Проверка границ не выглядит жёсткой."),
        "IMAGE": _extract_labeled_block(raw_text, "IMAGE", "Со стороны это читается достаточно нейтрально."),
        "RISKS": _extract_labeled_block(raw_text, "RISKS", "Сильных рисков не видно."),
        "NEXT_STEP": _extract_labeled_block(raw_text, "NEXT_STEP", "Лучше ответить спокойно и без давления."),
        "REACTION": _extract_labeled_block(raw_text, "REACTION", "Вероятна сдержанная реакция."),
    }

    if mode == "meaning":
        fields = [
            ("Что здесь, скорее всего, имеется в виду", parsed["MEANING"]),
            ("Настроение", parsed["MOOD"]),
            ("Интерес / холодность", parsed["INTEREST"]),
            ("Сомнение", parsed["DOUBT"]),
            ("Скрытые сигналы", parsed["SIGNALS"]),
            ("Проверка границ", parsed["BOUNDARY"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    elif mode == "risk":
        fields = [
            ("Риски", parsed["RISKS"]),
            ("Проверка границ", parsed["BOUNDARY"]),
            ("Интерес / холодность", parsed["INTEREST"]),
            ("Как это читается со стороны", parsed["IMAGE"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    elif mode == "before_send":
        fields = [
            ("Как это читается со стороны", parsed["IMAGE"]),
            ("Риски", parsed["RISKS"]),
            ("Проверка границ", parsed["BOUNDARY"]),
            ("Прогноз реакции", parsed["REACTION"]),
            ("Что лучше сделать", parsed["NEXT_STEP"]),
        ]
    elif mode == "reaction":
        fields = [
            ("Прогноз реакции", parsed["REACTION"]),
            ("Интерес / холодность", parsed["INTEREST"]),
            ("Скрытые сигналы", parsed["SIGNALS"]),
            ("Риски", parsed["RISKS"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
        ]
    else:
        fields = [
            ("Что здесь, скорее всего, имеется в виду", parsed["MEANING"]),
            ("Настроение", parsed["MOOD"]),
            ("Интерес / холодность", parsed["INTEREST"]),
            ("Сомнение", parsed["DOUBT"]),
            ("Скрытые сигналы", parsed["SIGNALS"]),
            ("Проверка границ", parsed["BOUNDARY"]),
            ("Как это читается со стороны", parsed["IMAGE"]),
            ("Риски", parsed["RISKS"]),
            ("Следующий лучший шаг", parsed["NEXT_STEP"]),
            ("Прогноз реакции", parsed["REACTION"]),
        ]

    return _format_sections(fields)


def analyze_dialog_v2(
    dialog_text: str,
    mode: str = "general",
    dialogue_context: str = "",
) -> str:
    if not dialog_text or not dialog_text.strip():
        return "Сначала пришли переписку для разбора."

    if mode not in DIALOG_MODE_INSTRUCTIONS:
        mode = "general"

    context_block = _build_context_block(dialogue_context)
    mode_instruction = DIALOG_MODE_INSTRUCTIONS[mode]

    prompt = (
        "Ты сильный аналитик переписки.\n"
        "Нужно разобрать диалог целиком.\n"
        f"{mode_instruction}\n"
        "Пиши коротко, по делу и без общих фраз.\n\n"
        "Верни ответ СТРОГО в формате:\n"
        "BALANCE: ...\n"
        "LEAD: ...\n"
        "INTEREST_DROP: ...\n"
        "PUSHINESS: ...\n"
        "DRYNESS: ...\n"
        "BEST_MESSAGES: ...\n"
        "WHAT_WENT_WRONG: ...\n"
        "DIALOG_SCORE: ...\n"
        "NEXT_STEP: ...\n\n"
        f"{context_block}"
        f"Диалог:\n{dialog_text}"
    )

    raw_text = _call_gigachat_text(prompt)

    parsed = {
        "BALANCE": _extract_labeled_block(raw_text, "BALANCE", "Баланс вклада сторон считывается неуверенно."),
        "LEAD": _extract_labeled_block(raw_text, "LEAD", "Не до конца ясно, кто стабильно ведёт разговор."),
        "INTEREST_DROP": _extract_labeled_block(raw_text, "INTEREST_DROP", "Явный момент просадки не считывается ярко."),
        "PUSHINESS": _extract_labeled_block(raw_text, "PUSHINESS", "Сильной навязчивости не видно."),
        "DRYNESS": _extract_labeled_block(raw_text, "DRYNESS", "Сильной сухости не видно."),
        "BEST_MESSAGES": _extract_labeled_block(raw_text, "BEST_MESSAGES", "Самые сильные сообщения не выделяются очень чётко."),
        "WHAT_WENT_WRONG": _extract_labeled_block(raw_text, "WHAT_WENT_WRONG", "Главный провал считывается не до конца."),
        "DIALOG_SCORE": _extract_labeled_block(raw_text, "DIALOG_SCORE", "Оценка выглядит средней."),
        "NEXT_STEP": _extract_labeled_block(raw_text, "NEXT_STEP", "Лучше сделать спокойный следующий шаг без давления."),
    }

    if mode == "dynamics":
        fields = [
            ("Кто вкладывается больше", parsed["BALANCE"]),
            ("Кто ведёт разговор", parsed["LEAD"]),
            ("Где переписка проседает", parsed["INTEREST_DROP"]),
            ("Оценка диалога", parsed["DIALOG_SCORE"]),
            ("Что делать дальше", parsed["NEXT_STEP"]),
        ]
    elif mode == "interest":
        fields = [
            ("Где падает интерес", parsed["INTEREST_DROP"]),
            ("Какие сообщения сработали лучше", parsed["BEST_MESSAGES"]),
            ("Оценка диалога", parsed["DIALOG_SCORE"]),
            ("Что пошло не так", parsed["WHAT_WENT_WRONG"]),
            ("Что делать дальше", parsed["NEXT_STEP"]),
        ]
    elif mode == "mistakes":
        fields = [
            ("Где ты выглядишь навязчиво", parsed["PUSHINESS"]),
            ("Где ты выглядишь сухо", parsed["DRYNESS"]),
            ("Что пошло не так", parsed["WHAT_WENT_WRONG"]),
            ("Оценка диалога", parsed["DIALOG_SCORE"]),
            ("Что делать дальше", parsed["NEXT_STEP"]),
        ]
    elif mode == "next_step":
        fields = [
            ("Оценка диалога", parsed["DIALOG_SCORE"]),
            ("Где просадка", parsed["INTEREST_DROP"]),
            ("Что пошло не так", parsed["WHAT_WENT_WRONG"]),
            ("Что сработало лучше", parsed["BEST_MESSAGES"]),
            ("Что делать дальше", parsed["NEXT_STEP"]),
        ]
    else:
        fields = [
            ("Кто вкладывается больше", parsed["BALANCE"]),
            ("Кто ведёт разговор", parsed["LEAD"]),
            ("Где падает интерес", parsed["INTEREST_DROP"]),
            ("Где ты выглядишь навязчиво", parsed["PUSHINESS"]),
            ("Где ты выглядишь сухо", parsed["DRYNESS"]),
            ("Какие сообщения сработали лучше", parsed["BEST_MESSAGES"]),
            ("Что пошло не так", parsed["WHAT_WENT_WRONG"]),
            ("Оценка диалога", parsed["DIALOG_SCORE"]),
            ("Что делать дальше", parsed["NEXT_STEP"]),
        ]

    return _format_sections(fields)


def get_gigachat_response(
    user_text: str,
    style: str = "friendly",
    variants_count: int = 3,
    dialogue_context: str = "",
) -> str:
    if not user_text or not user_text.strip():
        return "Сначала пришли текст."

    if style not in LEGACY_STYLE_PROMPTS:
        style = "friendly"

    try:
        variants_count = int(variants_count)
    except (TypeError, ValueError):
        variants_count = 3

    variants_count = max(1, min(variants_count, 3))
    context_block = _build_context_block(dialogue_context)

    prompt = (
        "Ты помощник по переписке.\n"
        f"Собери {variants_count} вариантов ответа.\n"
        f"Пиши {LEGACY_STYLE_PROMPTS[style]}.\n"
        "Пиши живо, естественно и без канцелярита.\n"
        "Верни только варианты, разделяя их строкой |||.\n\n"
        f"{context_block}"
        f"Сообщение:\n{user_text}"
    )

    raw_text = _call_gigachat_text(prompt)
    variants = _extract_variants(raw_text, variants_count)
    return _format_numbered_list(variants)