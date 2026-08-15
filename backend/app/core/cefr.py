"""Shared CEFR level labels and ordering."""

CEFR_LEVELS = ("PRE-A1", "A1", "A2", "B1", "B2", "C1", "C2")


def normalize_level_label(level: str) -> str:
    return level.strip().upper().replace(" ", "")


def level_index(level: str) -> int:
    normalized = normalize_level_label(level)
    try:
        return CEFR_LEVELS.index(normalized)
    except ValueError:
        return 0


def next_level(level: str) -> str | None:
    normalized = normalize_level_label(level)
    if normalized not in CEFR_LEVELS:
        return None
    index = CEFR_LEVELS.index(normalized)
    if index + 1 < len(CEFR_LEVELS):
        return CEFR_LEVELS[index + 1]
    return None


def previous_level(level: str) -> str | None:
    normalized = normalize_level_label(level)
    if normalized not in CEFR_LEVELS:
        return None
    index = CEFR_LEVELS.index(normalized)
    if index > 0:
        return CEFR_LEVELS[index - 1]
    return None


def levels_at_or_below(level: str) -> tuple[str, ...]:
    return CEFR_LEVELS[: level_index(level) + 1]
