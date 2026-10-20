"""Small local chat-reaction rules. No model calls, commands, logs, or storage."""

import re


def _text(value):
    value = value[:6000].casefold().replace("’", "'")
    # Code examples and quoted messages are poor clues to the speaker's mood.
    value = re.sub(r"```.*?(?:```|$)|`[^`]*`", " ", value, flags=re.S)
    value = re.sub(r"(?m)^\s*>.*$", " ", value)
    return re.sub(r"\s+", " ", value)


SUPPORT = re.compile(
    r"\b(?:sad|lonely|anxious|overwhelmed|heartbroken|scared|worried|grieving|upset|stressed|depressed|malungkot|nag-aalala|lungkot|namatayan)\b"
)
CELEBRATE = re.compile(
    r"\b(?:i (?:finally )?(?:passed|won|finished|graduated)|we (?:did it|won)|got (?:the|a new) job|congratulations|well done|proud of you|naipasa|nanalo)\b"
)
AFFECTION = re.compile(
    r"\b(?:thank(?:s| you)|love you|you're (?:so )?cute|you are (?:so )?cute|adorable|salamat|mahal kita|ang cute)\b|[🥰😘🧡❤️]"
)
LAUGH = re.compile(r"\b(?:ha(?:ha)+|lol|lmao|funny|joke|giggle|nakakatawa)\b|[😂🤣]")
SURPRISE = re.compile(
    r"\b(?:wow|whoa|unbelievable|surpris(?:e|ed|ing)|can't believe|gulat|grabe)\b|[😮😲]"
)
SLEEP = re.compile(r"\b(?:sleepy|good ?night|bedtime|time to sleep|antok|matulog)\b|😴")


def conversation_reaction(user_text, reply):
    """Choose only a known animation; the user's emotional cues take priority.

    This is deliberately a modest keyword/phrase heuristic, not a claim to read
    feelings. The setting and manual reaction menu remain under user control.
    """
    user, answer = _text(user_text), _text(reply)
    supported = re.sub(
        r"\b(?:not|never)\s+(?:feeling\s+)?(?:sad|lonely|anxious|worried|upset|stressed|depressed)\b",
        " ",
        user,
    )
    if SUPPORT.search(supported):
        return "comforting"
    for pattern, state in (
        (CELEBRATE, "dancing"),
        (AFFECTION, "bashful"),
        (LAUGH, "laughing"),
        (SURPRISE, "surprised"),
        (SLEEP, "yawning"),
    ):
        if pattern.search(user):
            return state
    if re.search(
        r"\b(?:sorry you're|sorry to hear|here for you|not alone|that sounds (?:hard|difficult)|sending (?:a )?hug)\b",
        answer,
    ):
        return "comforting"
    for pattern, state in (
        (CELEBRATE, "dancing"),
        (LAUGH, "laughing"),
        (SURPRISE, "surprised"),
    ):
        if pattern.search(answer):
            return state
    if "?" in user or re.search(
        r"\b(?:how|why|what|help|explain|paano|bakit|ano)\b", user
    ):
        return "curious"
    return "tail_wag"
