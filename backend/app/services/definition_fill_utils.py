"""Shared helpers for definition fill background jobs."""


def sanitize_fill_job_error_message(message: str | None) -> str | None:
    if not message:
        return None
    raw = message.split("\n", 1)[0].strip()
    lowered = raw.lower()
    if "database is locked" in lowered:
        return "Database was busy. Please start the fill job again."
    if "[sql:" in lowered or "parameters:" in lowered or len(raw) > 200:
        return "Definition fill stopped unexpectedly. Please try again."
    return raw[:200]


def fill_job_error_message_from_exception(exc: Exception) -> str:
    return sanitize_fill_job_error_message(str(exc)) or (
        "Definition fill stopped unexpectedly. Please try again."
    )
