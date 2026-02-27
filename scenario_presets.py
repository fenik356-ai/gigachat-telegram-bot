DEFAULT_SCENARIO_KEY = "neutral"

SCENARIO_OPTIONS = {
    "neutral": {
        "label": "Обычный",
        "instruction": "без специального сценария, просто уместно, естественно и по ситуации",
    },
    "dating_intro": {
        "label": "Знакомства",
        "instruction": "сценарий знакомства: легко, живо, без давления, с интересом и нормальной инициативой",
    },
    "restore_contact": {
        "label": "Вернуть контакт",
        "instruction": "сценарий возвращения контакта: мягко восстанови общение без неловкости и без навязчивости",
    },
    "business": {
        "label": "Деловая переписка",
        "instruction": "сценарий деловой переписки: чётко, уважительно, профессионально и без лишней воды",
    },
    "sales": {
        "label": "Продажи",
        "instruction": "сценарий продаж: усили ценность, снизь трение и мягко продвинь к следующему шагу",
    },
    "support": {
        "label": "Клиентский сервис",
        "instruction": "сценарий клиентского сервиса: спокойно, понятно, с заботой и ощущением контроля ситуации",
    },
    "soft_decline": {
        "label": "Отказ без конфликта",
        "instruction": "сценарий мягкого отказа: откажи ясно, вежливо и без лишнего напряжения",
    },
    "boundaries": {
        "label": "Постановка границ",
        "instruction": "сценарий границ: спокойно обозначь рамки, не переходя в агрессию и не оправдываясь слишком сильно",
    },
    "hard_talk": {
        "label": "Сложный разговор",
        "instruction": "сценарий сложного разговора: удержи уважение, ясность и контроль эмоций",
    },
    "rescue_chat": {
        "label": "Спаси переписку",
        "instruction": "сценарий спасения переписки: аккуратно оживи диалог, снизь неловкость и верни нормальный темп",
    },
    "first_message": {
        "label": "Что написать первым",
        "instruction": "сценарий первого сообщения: начни легко, естественно и так, чтобы было просто ответить",
    },
    "close_result": {
        "label": "Закрыть на результат",
        "instruction": "сценарий закрытия на результат: мягко, но уверенно веди к конкретному действию или решению",
    },
    "difficult_person": {
        "label": "Сложный человек",
        "instruction": "сценарий общения со сложным человеком: держи спокойствие, ясность и не поддавайся на эмоциональную раскачку",
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