MIN_VARIANTS = 3
MAX_VARIANTS = 7
DEFAULT_VARIANTS = 3

DEFAULT_TONE = "neutral"
DEFAULT_GOAL = "get_reply"


TONE_OPTIONS = {
    "neutral": {
        "label": "Обычный",
        "instruction": "сбалансированно, естественно и без лишней эмоциональности",
    },
    "shorter": {
        "label": "Короче",
        "instruction": "короче, плотнее и без лишних слов",
    },
    "softer": {
        "label": "Мягче",
        "instruction": "мягче, деликатнее и бережнее по тону",
    },
    "bolder": {
        "label": "Увереннее",
        "instruction": "увереннее, яснее и с более сильной позицией",
    },
    "warmer": {
        "label": "Теплее",
        "instruction": "теплее, человечнее и дружелюбнее",
    },
    "colder": {
        "label": "Холоднее",
        "instruction": "сдержаннее, суше и дистанцированнее",
    },
    "funnier": {
        "label": "Смешнее",
        "instruction": "чуть остроумнее и живее, но без клоунады",
    },
    "smarter": {
        "label": "Умнее",
        "instruction": "умнее, точнее, содержательнее и убедительнее",
    },
}


GOAL_OPTIONS = {
    "get_reply": {
        "label": "Получить ответ",
        "instruction": "сформулируй так, чтобы повысить шанс получить ответ",
    },
    "keep_interest": {
        "label": "Удержать интерес",
        "instruction": "сформулируй так, чтобы удержать внимание и интерес собеседника",
    },
    "book_meeting": {
        "label": "Закрыть на встречу",
        "instruction": "сформулируй так, чтобы аккуратно подвести к встрече или созвону",
    },
    "decline": {
        "label": "Отказать",
        "instruction": "сформулируй вежливый, ясный и корректный отказ",
    },
    "reconcile": {
        "label": "Помириться",
        "instruction": "сформулируй так, чтобы снизить напряжение и помочь восстановить контакт",
    },
    "sell": {
        "label": "Продать",
        "instruction": "сформулируй так, чтобы усилить ценность предложения и мягко продвинуть к покупке",
    },
}


def normalize_variants_count(value: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_VARIANTS

    if value < MIN_VARIANTS:
        return MIN_VARIANTS

    if value > MAX_VARIANTS:
        return MAX_VARIANTS

    return value


def get_tone_instruction(tone_key: str) -> str:
    if tone_key not in TONE_OPTIONS:
        tone_key = DEFAULT_TONE
    return TONE_OPTIONS[tone_key]["instruction"]


def get_goal_instruction(goal_key: str) -> str:
    if goal_key not in GOAL_OPTIONS:
        goal_key = DEFAULT_GOAL
    return GOAL_OPTIONS[goal_key]["instruction"]


def get_tone_label(tone_key: str) -> str:
    if tone_key not in TONE_OPTIONS:
        tone_key = DEFAULT_TONE
    return TONE_OPTIONS[tone_key]["label"]


def get_goal_label(goal_key: str) -> str:
    if goal_key not in GOAL_OPTIONS:
        goal_key = DEFAULT_GOAL
    return GOAL_OPTIONS[goal_key]["label"]


def get_default_module1_state() -> dict:
    return {
        "variants_count": DEFAULT_VARIANTS,
        "tone": DEFAULT_TONE,
        "goal": DEFAULT_GOAL,
    }