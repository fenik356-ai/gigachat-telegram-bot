from pathlib import Path
import py_compile
import sys


PROJECT_ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = [
    "main.py",
    "gigachat_api.py",
    ".env",
    "requirements.txt",
]

OPTIONAL_FILES = [
    "module1_reply_presets.py",
]

REQUIRED_ENV_KEYS = [
    "BOT_TOKEN",
    "GIGACHAT_CREDENTIALS",
]

RECOMMENDED_ENV_KEYS = [
    "GIGACHAT_SCOPE",
]


def read_env_file(env_path: Path) -> dict:
    data = {}

    if not env_path.exists():
        return data

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()

    return data


def check_files() -> list[str]:
    errors = []

    print("Проверка файлов проекта:")
    for file_name in REQUIRED_FILES:
        file_path = PROJECT_ROOT / file_name
        if file_path.exists():
            print(f"  [OK] {file_name}")
        else:
            print(f"  [X]  {file_name}")
            errors.append(f"Не найден обязательный файл: {file_name}")

    for file_name in OPTIONAL_FILES:
        file_path = PROJECT_ROOT / file_name
        if file_path.exists():
            print(f"  [INFO] Найден дополнительный файл: {file_name}")
        else:
            print(f"  [INFO] Дополнительный файл пока отсутствует: {file_name}")

    print()
    return errors


def check_env() -> list[str]:
    errors = []
    env_path = PROJECT_ROOT / ".env"
    env_data = read_env_file(env_path)

    print("Проверка .env:")

    if not env_path.exists():
        print("  [X]  Файл .env не найден")
        errors.append("Файл .env отсутствует")
        print()
        return errors

    print("  [OK] .env найден")

    for key in REQUIRED_ENV_KEYS:
        if env_data.get(key):
            print(f"  [OK] {key} задан")
        else:
            print(f"  [X]  {key} отсутствует или пустой")
            errors.append(f"В .env отсутствует обязательный ключ: {key}")

    for key in RECOMMENDED_ENV_KEYS:
        if env_data.get(key):
            print(f"  [OK] {key} задан")
        else:
            print(f"  [WARN] {key} не задан (рекомендуется добавить)")
    print()

    return errors


def check_python_syntax() -> list[str]:
    errors = []

    print("Проверка синтаксиса Python-файлов:")

    files_to_compile = [
        "main.py",
        "gigachat_api.py",
    ]

    optional_module = PROJECT_ROOT / "module1_reply_presets.py"
    if optional_module.exists():
        files_to_compile.append("module1_reply_presets.py")

    for file_name in files_to_compile:
        file_path = PROJECT_ROOT / file_name

        if not file_path.exists():
            continue

        try:
            py_compile.compile(str(file_path), doraise=True)
            print(f"  [OK] {file_name}")
        except Exception as e:
            print(f"  [X]  {file_name}")
            errors.append(f"Ошибка синтаксиса в {file_name}: {e}")

    print()
    return errors


def main():
    print("=== ПРОВЕРКА ТЕКУЩЕЙ БАЗЫ ПРОЕКТА ===")
    print()

    all_errors = []
    all_errors.extend(check_files())
    all_errors.extend(check_env())
    all_errors.extend(check_python_syntax())

    if all_errors:
        print("=== БАЗА ТРЕБУЕТ ИСПРАВЛЕНИЯ ===")
        print("Что нужно поправить:")
        for index, error in enumerate(all_errors, start=1):
            print(f"{index}. {error}")
        sys.exit(1)

    print("=== БАЗА ГОТОВА ===")
    print("Текущий проект можно безопасно дорабатывать дальше.")
    sys.exit(0)


if __name__ == "__main__":
    main()