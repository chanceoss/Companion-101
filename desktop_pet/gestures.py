"""One-shot reactions shared by the desktop, panel, and tray menus."""

GESTURES = (
    ("sitting", "Sit down"),
    ("stretching", "Stretch"),
    ("yawning", "Yawn"),
    ("dancing", "Dance"),
    ("hopping", "Playful hops"),
    ("tail_wag", "Wag tail"),
)
GESTURE_STATES = frozenset(state for state, _ in GESTURES)
