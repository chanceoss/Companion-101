"""UI-independent animation and movement. All time values are seconds."""
from dataclasses import dataclass
import math
from .animations import Animator, Pose


def clamp_position(x, y, left, top, right, bottom, width, height):
    """Keep window inside a screen's usable area, including negative monitor origins."""
    return (min(max(x, left), max(left, right - width)),
            min(max(y, top), max(top, bottom - height)))


@dataclass
class WalkMotion:
    """Float positions preserve smooth slow movement; right/bottom are exclusive."""
    x: float
    y: float
    vx: float
    vy: float

    def __post_init__(self):
        length = math.hypot(self.vx, self.vy)
        if not length or not math.isfinite(length):
            raise ValueError("A walking direction must be finite and nonzero.")
        self.vx /= length
        self.vy /= length

    @property
    def facing(self):
        if abs(self.vx) >= abs(self.vy):
            return "side"
        return "front" if self.vy > 0 else "back"

    @property
    def mirrored(self):
        return self.facing == "side" and self.vx < 0

    def step(self, dt, bounds, width, height, speed=42):
        left, top, right, bottom = bounds
        limit_x, limit_y = max(left, right - width), max(top, bottom - height)
        next_x = self.x + self.vx * max(0, dt) * speed
        next_y = self.y + self.vy * max(0, dt) * speed
        if next_x < left or next_x > limit_x:
            self.vx *= -1
        if next_y < top or next_y > limit_y:
            self.vy *= -1
        self.x = min(max(next_x, left), limit_x)
        self.y = min(max(next_y, top), limit_y)
        return round(self.x), round(self.y)


@dataclass
class FollowMotion:
    """Follow a pointer without overshooting, crossing monitors, or crowding it."""
    x: float
    y: float
    vx: float = 0
    vy: float = 1
    moving: bool = False

    @property
    def facing(self):
        if abs(self.vx) >= abs(self.vy):
            return "side"
        return "front" if self.vy > 0 else "back"

    def step(self, dt, pointer, bounds, width, height, speed=78):
        left, top, right, bottom = bounds
        px, py = pointer
        if not (left <= px < right and top <= py < bottom):
            self.moving = False
            return round(self.x), round(self.y)
        dx, dy = px - (self.x + width / 2), py - (self.y + height * .65)
        distance = math.hypot(dx, dy)
        # Hysteresis prevents repeated start/stop when the pointer barely moves.
        stop = max(70, width * .33)
        resume = stop + 25
        if distance <= stop or (not self.moving and distance < resume):
            self.moving = False
            return round(self.x), round(self.y)
        self.vx, self.vy = dx / distance, dy / distance
        travel = min(max(0, dt) * speed, distance - stop)
        x, y = clamp_position(self.x + self.vx * travel, self.y + self.vy * travel,
                              left, top, right, bottom, width, height)
        self.moving = math.hypot(x - self.x, y - self.y) > .001
        self.x, self.y = x, y
        return round(x), round(y)


def offline_reply(message, name="Biscuit"):
    words = message.lower()
    if any(x in words for x in ("sad", "lonely", "tired", "stress", "anxious")):
        return "I’m right here. Unclench your shoulders, take a slow breath, and let’s do one small thing at a time. 🧡"
    if any(x in words for x in ("hello", "hi", "hey")):
        return f"Hi, friend! I’m {name}. I’ve claimed this little corner of your desktop. How’s your day going?"
    if any(x in words for x in ("help", "can you", "how to")):
        return "Drag me anywhere, double-click me to open this window, or right-click for my menu. Turn on wandering if you’d like a little company while you work."
    if any(x in words for x in ("love", "cute", "good")):
        return "You’ve made my little tail very happy! Consider this a tiny high-five. 🐾"
    if any(x in words for x in ("break", "water", "focus", "work")):
        return "Tiny mission: a sip of water, a stretch, then one focused step. I’ll keep you company."
    return "I’m listening, with both fuzzy ears. In offline mode I have a few cozy replies; connect an AI provider in Preferences for open-ended conversation."
