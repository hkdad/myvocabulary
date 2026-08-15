import random

try:
    import pyphen
except ImportError:  # pragma: no cover - optional at runtime until deps installed
    pyphen = None

GIVE_UP_MARKER = "__GIVE_UP__"


def normalize_answer(value: str) -> str:
    return value.strip().lower()


def score_answer(expected: str, submitted: str) -> bool:
    return normalize_answer(expected) == normalize_answer(submitted)


def generate_choices(correct_word: str, pool: list[str], *, count: int = 4) -> list[str]:
    """Build shuffled multiple-choice options including the correct word."""
    distractors = [
        word for word in pool if normalize_answer(word) != normalize_answer(correct_word)
    ]
    random.shuffle(distractors)
    options = [correct_word, *distractors[: max(0, count - 1)]]
    random.shuffle(options)
    return options


def hint_for_word(word: str) -> str:
    if not word:
        return ""
    return f"Starts with: {word[0].upper()}"


def split_syllables(word: str) -> list[str]:
    cleaned = word.strip()
    if not cleaned:
        return []

    if pyphen is not None:
        dic = pyphen.Pyphen(lang="en_US")
        hyphenated = dic.inserted(cleaned.lower())
        parts = [part for part in hyphenated.split("-") if part]
        if parts:
            return parts

    if len(cleaned) <= 3:
        return [cleaned.lower()]

    chunks: list[str] = []
    current = ""
    vowels = set("aeiouy")
    for index, char in enumerate(cleaned.lower()):
        current += char
        next_char = cleaned.lower()[index + 1] if index + 1 < len(cleaned) else ""
        if char in vowels and next_char and next_char not in vowels:
            chunks.append(current)
            current = ""
    if current:
        if chunks:
            chunks[-1] += current
        else:
            chunks = [current]
    return chunks or [cleaned.lower()]
