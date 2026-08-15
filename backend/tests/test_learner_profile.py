"""Tests for learner profile emoji helpers."""

from app.services.learner_profile import resolve_learner_emoji


def test_resolve_learner_emoji_uses_stored_value() -> None:
    assert resolve_learner_emoji("🦊", "Leo") == "🦊"


def test_resolve_learner_emoji_default_without_stored_value() -> None:
    assert resolve_learner_emoji(None, "Mia") == "🌟"
    assert resolve_learner_emoji(None, "Leo") == "🌟"
    assert resolve_learner_emoji("", None) == "🌟"
