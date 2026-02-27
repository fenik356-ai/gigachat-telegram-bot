DEFAULT_SCENARIO_KEY = "neutral"

SCENARIO_OPTIONS = {
    "neutral": {
        "label": "Обычный",
        "instruction": "без специального сценария, просто уместно, естественно и по ситуации",
        "default_tone": "neutral",
        "default_goal": "get_reply",
        "default_variants": 3,
        "starter_hint": "Опиши ситуацию обычным текстом — я предложу уместный ответ.",
    },
    "dating_intro": {
        "label": "Знакомства",
        "instruction": "сценарий знакомства: легко, живо, без давления, с интересом и нормальной инициативой",
        "default_tone": "warmer",
        "default_goal": "keep_interest",
        "default_variants": 4,
        "starter_hint": "Например: «Помоги ответить так, чтобы разговор пошёл живее».",
    },
    "relationships": {
        "label": "Отношения",
        "instruction": "сценарий отношений: бережно, честно, по-человечески, без лишней драмы",
        "default_tone": "warmer",
        "default_goal": "reconcile",
        "default_variants": 4,
        "starter_hint": "Например: «Нужно спокойно обсудить важное и не усугубить».",
    },
    "restore_contact": {
        "label": "Вернуть контакт",
        "instruction": "сценарий возвращения контакта: мягко восстанови общение без неловкости и без навязчивости",
        "default_tone": "softer",
        "default_goal": "reconcile",
        "default_variants": 4,
        "starter_hint": "Например: «Хочу написать после паузы и не выглядеть странно».",
    },
    "reconcile_chat": {
        "label": "Помириться",
        "instruction": "сценарий примирения: снизь напряжение, сохрани уважение и оставь место для диалога",
        "default_tone": "softer",
        "default_goal": "reconcile",
        "default_variants": 4,
        "starter_hint": "Например: «Нужно помириться без давления и лишнего пафоса».",
    },
    "first_message": {
        "label": "Не знаю, что написать первым",
        "instruction": "сценарий первого сообщения: начни легко, естественно и так, чтобы было просто ответить",
        "default_tone": "warmer",
        "default_goal": "keep_interest",
        "default_variants": 4,
        "starter_hint": "Например: «Что написать первым, чтобы это звучало легко?».",
    },
    "rescue_chat": {
        "label": "Спаси переписку",
        "instruction": "сценарий спасения переписки: аккуратно оживи диалог, снизь неловкость и верни нормальный темп",
        "default_tone": "warmer",
        "default_goal": "keep_interest",
        "default_variants": 4,
        "starter_hint": "Например: «Переписка затухла — как оживить её без кринжа?».",
    },
    "business": {
        "label": "Деловая переписка",
        "instruction": "сценарий деловой переписки: чётко, уважительно, профессионально и без лишней воды",
        "default_tone": "smarter",
        "default_goal": "get_reply",
        "default_variants": 3,
        "starter_hint": "Например: «Нужно ответить по делу, коротко и понятно».",
    },
    "sales": {
        "label": "Продажи",
        "instruction": "сценарий продаж: усили ценность, снизь трение и мягко продвинь к следующему шагу",
        "default_tone": "bolder",
        "default_goal": "sell",
        "default_variants": 4,
        "starter_hint": "Например: «Нужно подвести клиента к следующему шагу без давления».",
    },
    "support": {
        "label": "Клиентский сервис",
        "instruction": "сценарий клиентского сервиса: спокойно, понятно, с заботой и ощущением контроля ситуации",
        "default_tone": "softer",
        "default_goal": "get_reply",
        "default_variants": 3,
        "starter_hint": "Например: «Нужно ответить клиенту спокойно и снять напряжение».",
    },
    "close_result": {
        "label": "Закрыть на результат",
        "instruction": "сценарий закрытия на результат: мягко, но уверенно веди к конкретному действию или решению",
        "default_tone": "bolder",
        "default_goal": "book_meeting",
        "default_variants": 4,
        "starter_hint": "Например: «Помоги подвести к созвону или чёткому решению».",
    },
    "soft_decline": {
        "label": "Отказ без конфликта",
        "instruction": "сценарий мягкого отказа: откажи ясно, вежливо и без лишнего напряжения",
        "default_tone": "softer",
        "default_goal": "decline",
        "default_variants": 3,
        "starter_hint": "Например: «Нужно отказаться и не испортить отношения».",
    },
    "boundaries": {
        "label": "Постановка границ",
        "instruction": "сценарий границ: спокойно обозначь рамки, не переходя в агрессию и не оправдываясь слишком сильно",
        "default_tone": "bolder",
        "default_goal": "decline",
        "default_variants": 3,
        "starter_hint": "Например: «Нужно спокойно обозначить границы и не сорваться».",
    },
    "hard_talk": {
        "label": "Сложный разговор",
        "instruction": "сценарий сложного разговора: удержи уважение, ясность и контроль эмоций",
        "default_tone": "smarter",
        "default_goal": "reconcile",
        "default_variants": 4,
        "starter_hint": "Например: «Нужно обсудить сложное спокойно и без эскалации».",
    },
    "difficult_person": {
        "label": "Сложный человек",
        "instruction": "сценарий общения со сложным человеком: держи спокойствие, ясность и не поддавайся на эмоциональную раскачку",
        "default_tone": "smarter",
        "default_goal": "decline",
        "default_variants": 3,
        "starter_hint": "Например: «Нужно ответить спокойно и не втянуться в конфликт».",
    },
}


def _safe_key(scenario_key: str) -> str:
    if scenario_key not in SCENARIO_OPTIONS:
        return DEFAULT_SCENARIO_KEY
    return scenario_key


def get_scenario_label(scenario_key: str) -> str:
    key = _safe_key(scenario_key)
    return SCENARIO_OPTIONS[key]["label"]


def get_scenario_instruction(scenario_key: str) -> str:
    key = _safe_key(scenario_key)
    return SCENARIO_OPTIONS[key]["instruction"]


def get_scenario_defaults(scenario_key: str) -> dict:
    key = _safe_key(scenario_key)
    item = SCENARIO_OPTIONS[key]

    return {
        "tone": item["default_tone"],
        "goal": item["default_goal"],
        "variants": item["default_variants"],
    }


def get_scenario_starter_hint(scenario_key: str) -> str:
    key = _safe_key(scenario_key)
    return SCENARIO_OPTIONS[key]["starter_hint"]