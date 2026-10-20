"""One-shot reactions shared by the desktop, panel, and tray menus."""

CLASSIC_GESTURES = (
    ("sitting", "Sit down"),
    ("stretching", "Stretch"),
    ("yawning", "Yawn"),
    ("dancing", "Dance"),
    ("hopping", "Playful hops"),
    ("tail_wag", "Wag tail"),
)
CONVERSATION_GESTURES = (
    ("thinking", "Thinking"),
    ("curious", "All ears"),
    ("laughing", "Giggle"),
    ("surprised", "Surprised"),
    ("comforting", "A little comfort"),
    ("bashful", "Blushing"),
)
GESTURES = CLASSIC_GESTURES + CONVERSATION_GESTURES
# This loop is owned by the chat request lifecycle, never a manual menu action.
GESTURE_STATES = frozenset(state for state, _ in GESTURES) | {"chat_thinking"}
