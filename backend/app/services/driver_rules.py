import re

DRIVER_CATEGORY_KEYS = ("A", "B", "C", "D", "BE", "CE", "DE", "Tm", "Tb", "M", "A1", "B1", "C1", "D1", "C1E", "D1E")
DRIVER_EXTENDED_CATEGORIES = {"C", "D", "CE", "DE", "C1", "D1", "C1E", "D1E", "Tm", "Tb"}
# Открытая категория открывает и свою подкатегорию, и M: отметили B — в справке
# появляются B, B1, M. То же правило продублировано в demo/app.js.
DRIVER_IMPLIED_CATEGORIES = {
    "A": ("A1", "M"),
    "B": ("B1", "M"),
    "C": ("C1", "M"),
    "D": ("D1", "M"),
}


def expand_implied_driver_categories(categories: set[str]) -> set[str]:
    expanded = set(categories)
    for category, implied in DRIVER_IMPLIED_CATEGORIES.items():
        if category in expanded:
            expanded.update(implied)
    return expanded


def driver_category_tokens(value: object) -> set[str]:
    text = str(value or "")
    raw_tokens = re.findall(r"[A-Za-zА-Яа-я0-9]+", text)
    aliases = {
        "А": "A",
        "Б": "B",
        "В": "B",
        "С": "C",
        "Д": "D",
        "1A": "A1",
        "1B": "B1",
        "1C": "C1",
        "1D": "D1",
        "1CE": "C1E",
        "1DE": "D1E",
        "Е": "E",
        "ВЕ": "BE",
        "СЕ": "CE",
        "ДЕ": "DE",
    }
    tokens: set[str] = set()
    for token in raw_tokens:
        normalized = aliases.get(token.upper(), token)
        normalized = {"TM": "Tm", "TB": "Tb"}.get(normalized.upper(), normalized.upper())
        if normalized in DRIVER_CATEGORY_KEYS or normalized == "E":
            tokens.add(normalized)
    if "E" in tokens:
        tokens.update({"BE", "CE", "DE"})
    return expand_implied_driver_categories(tokens)


def certificate_doctor_roles(categories: object) -> set[str]:
    roles = {"therapist", "ophthalmologist"}
    if driver_category_tokens(categories) & DRIVER_EXTENDED_CATEGORIES:
        roles.update({"neurologist", "otolaryngologist"})
    return roles


def is_driver_or_tractor_service(service: object) -> bool:
    name = str(getattr(service, "name", "") or "").lower()
    return getattr(service, "legacy_source_id", None) in {7, 8, 29} or "водител" in name or "трактор" in name or "071" in name
