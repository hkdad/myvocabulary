DEFAULT_LEARNER_EMOJI = "🌟"


def resolve_learner_emoji(emoji: str | None, display_name: str | None = None) -> str:
    del display_name  # Callers may pass a name; emoji is explicit or default.
    if emoji and emoji.strip():
        return emoji.strip()
    return DEFAULT_LEARNER_EMOJI
