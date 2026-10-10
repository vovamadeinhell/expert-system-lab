from dataclasses import dataclass
from pathlib import Path
import re


RULES_FILE = Path(__file__).with_name("rules.txt")
GOAL = "Диагноз"


@dataclass(frozen=True)
class Rule:
    conditions: tuple[tuple[str, str], ...]
    conclusion: tuple[str, str]

    def __str__(self) -> str:
        left = " И ".join(f"{name}={value}" for name, value in self.conditions)
        name, value = self.conclusion
        return f"ЕСЛИ {left} ТО {name}={value}"


def parse_pair(text: str) -> tuple[str, str]:
    if text.count("=") != 1:
        raise ValueError(f"Некорректная пара Объект=Значение: {text}")
    name, value = (part.strip() for part in text.split("=", 1))
    if not name or not value:
        raise ValueError(f"Объект и значение не должны быть пустыми: {text}")
    return name, value


def parse_rule(line: str) -> Rule:
    match = re.fullmatch(r"\s*ЕСЛИ\s+(.+?)\s+ТО\s+(.+?)\s*", line)
    if not match:
        raise ValueError("Ожидается формат: ЕСЛИ ... ТО Объект=Значение")

    conditions = tuple(
        parse_pair(part)
        for part in re.split(r"\s+И\s+", match.group(1))
    )
    if not conditions:
        raise ValueError("У правила должно быть хотя бы одно условие")

    return Rule(conditions, parse_pair(match.group(2)))


def load_rules(path: Path = RULES_FILE) -> list[Rule]:
    rules = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        content = line.strip()
        if not content or content.startswith("#"):
            continue
        try:
            rules.append(parse_rule(content))
        except ValueError as error:
            raise ValueError(
                f"Ошибка в файле правил, строка {line_number}: {error}"
            ) from error
    return rules


def save_rules(rules: list[Rule], path: Path = RULES_FILE) -> None:
    path.write_text(
        "\n".join(str(rule) for rule in rules) + "\n",
        encoding="utf-8",
    )


def print_rules(rules: list[Rule]) -> None:
    print("\n=== БАЗА ПРАВИЛ ===")
    if not rules:
        print("Правила отсутствуют.")
        return
    for i, rule in enumerate(rules, 1):
        print(f"{i}. {rule}")


def print_facts(facts: dict[str, str]) -> None:
    print("\n=== РАБОЧАЯ БАЗА ДАННЫХ ===")
    if not facts:
        print("Факты отсутствуют.")
        return
    for name, value in facts.items():
        print(f"{name} = {value}")


def merge_question_paths(
    left: tuple[tuple[str, str], ...],
    right: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Объединяет условия двух частей цепочки без повторов."""
    return tuple(dict.fromkeys((*left, *right)))


def question_paths_for_fact(
    rules: list[Rule],
    facts: dict[str, str],
    fact: tuple[str, str],
    visiting: frozenset[tuple[str, str]] = frozenset(),
) -> list[tuple[tuple[str, str], ...]]:
    """Находит варианты вопросов, необходимые для получения заданного факта."""
    name, value = fact

    if name in facts:
        return [()] if facts[name] == value else []
    if fact in visiting:
        return []

    producers = [rule for rule in rules if rule.conclusion == fact]
    if not producers:
        return [(fact,)]

    paths: list[tuple[tuple[str, str], ...]] = []
    next_visiting = visiting | {fact}

    for rule in producers:
        rule_paths: list[tuple[tuple[str, str], ...]] = [()]
        for condition in rule.conditions:
            condition_paths = question_paths_for_fact(
                rules, facts, condition, next_visiting
            )
            if not condition_paths:
                rule_paths = []
                break
            rule_paths = [
                merge_question_paths(left, right)
                for left in rule_paths
                for right in condition_paths
            ]
        paths.extend(rule_paths)

    return list(dict.fromkeys(paths))


def question_paths_for_goal(
    rules: list[Rule],
    facts: dict[str, str],
    goal: str,
) -> list[tuple[tuple[str, str], ...]]:
    """Строит возможные цепочки вопросов, ведущие к целевому объекту."""
    if goal in facts:
        return []

    paths: list[tuple[tuple[str, str], ...]] = []
    for rule in rules:
        if rule.conclusion[0] != goal:
            continue

        rule_paths: list[tuple[tuple[str, str], ...]] = [()]
        for condition in rule.conditions:
            condition_paths = question_paths_for_fact(
                rules, facts, condition
            )
            if not condition_paths:
                rule_paths = []
                break
            rule_paths = [
                merge_question_paths(left, right)
                for left in rule_paths
                for right in condition_paths
            ]
        paths.extend(rule_paths)

    return list(dict.fromkeys(paths))


def next_question(
    rules: list[Rule],
    facts: dict[str, str],
    goal: str = GOAL,
) -> tuple[str, str] | None:
    """Берёт первый неизвестный факт из кратчайшей цепочки к цели."""
    paths = question_paths_for_goal(rules, facts, goal)
    nonempty_paths = [path for path in paths if path]
    if not nonempty_paths:
        return None
    return min(nonempty_paths, key=len)[0]


def forward_chain(
    rules: list[Rule],
    facts: dict[str, str],
    ask_fact,
) -> tuple[dict[str, str], list[str]]:
    """Выполняет прямой вывод и динамически запрашивает недостающие факты."""
    working_memory = dict(facts)
    trace: list[str] = []
    fired: set[int] = set()

    while True:
        fired_this_pass = False

        for index, rule in enumerate(rules):
            if index in fired:
                continue

            if all(
                working_memory.get(name) == value
                for name, value in rule.conditions
            ):
                name, value = rule.conclusion
                fired.add(index)

                if name not in working_memory:
                    working_memory[name] = value
                    kind = "итоговый диагноз" if name == GOAL else "промежуточный факт"
                    trace.append(
                        f"Сработало правило {index + 1}: {rule}; "
                        f"в рабочую базу добавлен {kind} {name}={value}"
                    )
                    fired_this_pass = True
                elif working_memory[name] != value:
                    trace.append(
                        f"Правило {index + 1}: заключение {name}={value} "
                        f"не добавлено, так как {name} уже имеет значение "
                        f"{working_memory[name]}"
                    )

        if GOAL in working_memory:
            break

        if fired_this_pass:
            continue

        missing = next_question(rules, working_memory)
        if missing is None:
            trace.append(
                "В базе знаний нет доступной цепочки правил, "
                "которая может привести к целевому диагнозу."
            )
            break

        name, expected_value = missing
        supplied = ask_fact(name, expected_value)
        if supplied is None or not str(supplied).strip():
            trace.append(
                f"Данные для факта «{name}» не получены. Вывод завершён."
            )
            break

        working_memory[name] = str(supplied).strip().lower()
        trace.append(
            f"Пользователь сообщил факт {name}={working_memory[name]} "
            f"(в выбранной цепочке проверяется значение "
            f"{expected_value})"
        )

    return working_memory, trace


def ask_fact(name: str, expected_value: str) -> str:
    return input(
        f"\nВопрос системы: какое значение имеет «{name}»? "
        f"Для выбранной цепочки ожидается «{expected_value}» "
        "(Enter — завершить): "
    ).strip()


def run_expert_system() -> None:
    try:
        rules = load_rules()
    except ValueError as error:
        print(f"\nОшибка загрузки базы правил: {error}")
        return

    facts: dict[str, str] = {}
    print("\n=== КОНСУЛЬТАЦИЯ ===")
    print(
        "Рабочая база начинается пустой. Система задаёт вопросы "
        "по текущим правилам и цели «Диагноз»."
    )
    print_facts(facts)

    result, trace = forward_chain(rules, facts, ask_fact)

    print("\n=== ХОД ПРЯМОГО ВЫВОДА ===")
    if trace:
        for item in trace:
            print(f"- {item}")
    else:
        print("Ни одно правило не сработало.")

    print_facts(result)

    print("\n=== РЕЗУЛЬТАТ ===")
    if GOAL in result:
        print(f"Диагноз: {result[GOAL]}")
    else:
        print("Определённый диагноз получить не удалось.")


def add_rule(rules: list[Rule]) -> None:
    print("\nВведите правило, заменив пример конкретными признаками:")
    print("ЕСЛИ Компьютер_включается=да И Корпус_перегревается=да "
          "ТО Диагноз=вероятный_перегрев_компьютера")
    line = input("> ").strip()

    try:
        rule = parse_rule(line)
    except ValueError as error:
        print(f"Ошибка: {error}")
        return

    pairs = (*rule.conditions, rule.conclusion)
    if any(
        name.casefold() == "объект" and value.casefold() == "значение"
        for name, value in pairs
    ):
        print(
            "Ошибка: введён шаблон. Замените «Объект» и «Значение» "
            "конкретными признаками и значениями. Правило не сохранено."
        )
        return

    rules.append(rule)
    save_rules(rules)
    if rule.conclusion[0] == GOAL:
        print(
            "Правило добавлено. Если его условия выполнятся, оно сможет "
            "вывести указанный диагноз. Неизвестные условия система "
            "сможет спросить при следующей консультации."
        )
    else:
        print(
            "Правило добавлено. Оно повлияет на диагноз, если его "
            "заключение используется в другой цепочке, ведущей к «Диагноз»."
        )


def edit_rule(rules: list[Rule]) -> None:
    print_rules(rules)
    if not rules:
        return

    try:
        index = int(input("Номер правила для изменения: ")) - 1
        if not 0 <= index < len(rules):
            raise ValueError
    except ValueError:
        print("Некорректный номер.")
        return

    print(f"Текущее правило: {rules[index]}")
    line = input("Новое правило: ").strip()

    try:
        rules[index] = parse_rule(line)
    except ValueError as error:
        print(f"Ошибка: {error}")
        return

    save_rules(rules)
    print("Правило изменено.")


def delete_rule(rules: list[Rule]) -> None:
    print_rules(rules)
    if not rules:
        return

    try:
        index = int(input("Номер правила для удаления: ")) - 1
        if not 0 <= index < len(rules):
            raise ValueError
    except ValueError:
        print("Некорректный номер.")
        return

    deleted = rules.pop(index)
    save_rules(rules)
    print(f"Удалено правило: {deleted}")


def rules_menu() -> None:
    try:
        rules = load_rules()
    except ValueError as error:
        print(f"Ошибка загрузки базы правил: {error}")
        return

    while True:
        print("\n=== РЕДАКТИРОВАНИЕ БАЗЫ ПРАВИЛ ===")
        print("1. Показать правила")
        print("2. Добавить правило")
        print("3. Изменить правило")
        print("4. Удалить правило")
        print("0. Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            print_rules(rules)
        elif choice == "2":
            add_rule(rules)
        elif choice == "3":
            edit_rule(rules)
        elif choice == "4":
            delete_rule(rules)
        elif choice == "0":
            break
        else:
            print("Неизвестная команда.")


def main() -> None:
    while True:
        print("\n" + "=" * 55)
        print("ЭКСПЕРТНАЯ СИСТЕМА: ДИАГНОСТИКА КОМПЬЮТЕРА")
        print("=" * 55)
        print("1. Запустить экспертную систему")
        print("2. Показать рабочую базу правил")
        print("3. Редактировать базу правил")
        print("0. Выход")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            run_expert_system()
        elif choice == "2":
            try:
                print_rules(load_rules())
            except ValueError as error:
                print(f"Ошибка: {error}")
        elif choice == "3":
            rules_menu()
        elif choice == "0":
            print("Работа завершена.")
            break
        else:
            print("Неизвестная команда.")


if __name__ == "__main__":
    main()
