DEFAULT_SCENARIO_KEY = "neutral"

SCENARIO_OPTIONS = {
    "neutral": {
        "label": "Обычный",
        "instruction": "без специального сценария, просто уместно, естественно и по ситуации",
        "default_tone": "neutral",
        "default_goal": "get_reply",
        "default_variants": 3,
        "starter_hint": "Опиши ситуацию обычным текстом, и бот предложит уместные варианты ответа.",
    },
    "dating_intro": {
        "label": "Знакомства",
        "instruction": "сценарий знакомства: легко, живо, без давления, с интересом и нормальной инициативой",
        "default_tone": "warmer",
        "default_goal": "keep_interest",
        "default_variants": 4,
        "starter_hint": "Например: «Помоги ответить на первое сообщение так, чтобы разговор пошёл живее».",
    },
    "restore_contact": {
        "label": "Вернуть контакт",
        "instruction": "сценарий возвращения контакта: мягко восстанови общение без неловкости и без навязчивости",
        "default_tone": "softer",
        "default_goal": "reconcile",
        "default_variants": 4,
        "starter_hint": "Например: «Нужно аккуратно написать человеку после долгой паузы».",
    },
    "business": {
        "label": "Деловая переписка",
        "instruction": "сценарий деловой переписки: чётко, уважительно, профессионально и без лишней воды",
        "default_tone": "smarter",
        "default_goal": "get_reply",
        "default_variants": 3,
        "starter_hint": "Например: «Помоги ответить клиенту по делу и без лишней воды».",
    },
    "sales": {
        "label": "Продажи",
        "instruction": "сценарий продаж: усили ценность, снизь трение и мягко продвинь к следующему шагу",
        "default_tone": "bolder",
        "default_goal": "sell",
        "default_variants": 4,
        "starter_hint": "Например: «Нужно подвести клиента к покупке без жёсткого давления».",
    },
    "support": {
        "label": "Клиентский сервис",
        "instruction": "сценарий клиентского сервиса: спокойно, понятно, с заботой и ощущением контроля ситуации",
        "default_tone": "softer",
        "default_goal": "get_reply",
        "default_variants": 3,
        "starter_hint": "Например: «Помоги ответить клиенту спокойно и понятно, чтобы снять напряжение».",
    },
    "soft_decline": {
        "label": "Отказ без конфликта",
        "instruction": "сценарий мягкого отказа: откажи ясно, вежливо и без лишнего напряжения",
        "default_tone": "softer",
        "default_goal": "decline",
        "default_variants": 3,
        "starter_hint": "Например: «Нужно вежливо отказаться, не испортив отношения».",
    },
    "boundaries": {
        "label": "Постановка границ",
        "instruction": "сценарий границ: спокойно обозначь рамки, не переходя в агрессию и не оправдываясь слишком сильно",
        "default_tone": "bolder",
        "default_goal": "decline",
        "default_variants": 3,
        "starter_hint": "Например: «Помоги спокойно обозначить границы без грубости».",
    },
    "hard_talk": {
        "label": "Сложный разговор",
        "instruction": "сценарий сложного разговора: удержи уважение, ясность и контроль эмоций",
        "default_tone": "smarter",
        "default_goal": "reconcile",
        "default_variants": 4,
        "starter_hint": "Например: «Нужно ответить на сложную тему спокойно и без эскалации».",
    },
    "rescue_chat": {
        "label": "Спаси переписку",
        "instruction": "сценарий спасения переписки: аккуратно оживи диалог, снизь неловкость и верни нормальный темп",
        "default_tone": "warmer",
        "default_goal": "keep_interest",
        "default_variants": 4,
        "starter_hint": "Например: «Переписка затухла — как оживить её без кринжа?».",
    },
    "first_message": {
        "label": "Что написать первым",
        "instruction": "сценарий первого сообщения: начни легко, естественно и так, чтобы было просто ответить",
        "default_tone": "warmer",
        "default_goal": "keep_interest",
        "default_variants": 4,
        "starter_hint": "Например: «Что написать первым, чтобы было легко ответить?».",
    },
    "close_result": {
        "label": "Закрыть на результат",
        "instruction": "сценарий закрытия на результат: мягко, но уверенно веди к конкретному действию или решению",
        "default_tone": "bolder",
        "default_goal": "book_meeting",
        "default_variants": 4,
        "starter_hint": "Например: «Помоги подвести к созвону или чёткому решению».",
    },
    "difficult_person": {
        "label": "Сложный человек",
        "instruction": "сценарий общения со сложным человеком: держи спокойствие, ясность и не поддавайся на эмоциональную раскачку",
        "default_tone": "smarter",
        "default_goal": "decline",
        "default_variants": 3,
        "starter_hint": "Например: «Нужно ответить сложному человеку спокойно и без лишних эмоций».",
    },
}


def get_scenario_label(scenario_key: str) -> str:
    if scenario_key not in SCENARIO_OPTIONS:
        scenario_key = DEFAULT_SCENARIO_KEY
    return SCENARIO_OPTIONS[scenario_key]["label"]


def get_scenario_instruction(scenario_key: str) -> str:
    if scenario_key not in SCENARIO_OPTIONS:
        scenario_key = DEFAULT_SCENARIO_KEY
    return SCENARIO_OPTIONS[scenario_key]["instruction"]


def get_scenario_defaults(scenario_key: str) -> dict:
    if scenario_key not in SCENARIO_OPTIONS:
        scenario_key = DEFAULT_SCENARIO_KEY

    item = SCENARIO_OPTIONS[scenario_key]

    return {
        "tone": item["default_tone"],
        "goal": item["default_goal"],
        "variants": item["default_variants"],
    }


def get_scenario_starter_hint(scenario_key: str) -> str:
    if scenario_key not in SCENARIO_OPTIONS:
        scenario_key = DEFAULT_SCENARIO_KEY
    return SCENARIO_OPTIONS[scenario_key]["starter_hint"]