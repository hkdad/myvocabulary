from app.services.definition_fill_utils import (
    fill_job_error_message_from_exception,
    sanitize_fill_job_error_message,
)


def test_sanitize_fill_job_error_message_hides_sql_parameters() -> None:
    raw = (
        '(sqlite3.OperationalError) database is locked\n'
        "[SQL: UPDATE definition_fill_jobs SET failed_words_json=?, "
        'error_message=? WHERE id = ?]\n'
        '[parameters: (\'[{"word": "mortimer", "entry_id": 5171}\', None, 6)]'
    )
    assert sanitize_fill_job_error_message(raw) == (
        "Database was busy. Please start the fill job again."
    )


def test_sanitize_fill_job_error_message_truncates_long_messages() -> None:
    assert sanitize_fill_job_error_message("x" * 300) == (
        "Definition fill stopped unexpectedly. Please try again."
    )


def test_fill_job_error_message_from_exception() -> None:
    assert fill_job_error_message_from_exception(RuntimeError("network timeout")) == (
        "network timeout"
    )
