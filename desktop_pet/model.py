"""UI-independent animation and movement. All time values are seconds."""
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class Pose:
    bob: float = 0
    rotation: float = 0
    sx: float = 1
    sy: float = 1
    opacity: float = 1
    blink: bool = False


class Animator:
    def __init__(self, walk_fps=8, walk_frames=4):
        self.state = "entering"
        self.elapsed = 0.0
        self.clock = 0.0
        self.blink_at = 2.8
        self.rng = random.Random()
        self.walk_fps = walk_fps
        self.walk_frames = max(1, walk_frames)

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.elapsed = 0.0

    def advance(self, dt):
        self.elapsed += max(0, dt)
        self.clock += max(0, dt)
        if self.clock > self.blink_at + .16:
            self.blink_at = self.clock + self.rng.uniform(2.5, 6)
        if self.state in ("entering", "happy") and self.elapsed > (0.65 if self.state == "entering" else 1.5):
            self.set_state("idle")
        t = self.elapsed
        blink = self.blink_at <= self.clock <= self.blink_at + .16
        if self.state == "walking":
            # Secondary motion follows the gait instead of rocking the whole body.
            wave = math.sin(t * math.tau * self.walk_fps / self.walk_frames)
            return Pose(-abs(wave) * 2, wave * 1.2, 1 + abs(wave) * .008, 1 - abs(wave) * .008, blink=blink)
        if self.state == "happy":
            wave = math.sin(t * 16)
            return Pose(-abs(wave) * 16, wave * 6, 1 + wave * .035, 1 - wave * .035, blink=blink)
        if self.state == "sleeping":
            return Pose(2, -5, 1.04, .93 + math.sin(t * 2) * .012, blink=True)
        if self.state == "dragged":
            return Pose(0, math.sin(t * 9) * 9, .95, 1.05, blink=blink)
        if self.state in ("entering", "leaving"):
            f = min(1, t / .6)
            if self.state == "leaving":
                f = 1 - f
            return Pose((1 - f) * 80, (1 - f) * -12, .75 + .25 * f, .75 + .25 * f, f, blink)
        breath = math.sin(t * 2.4)
        return Pose(breath * 1.4, math.sin(t * 1.2) * .6, 1 + breath * .004, 1 - breath * .006, blink=blink)


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
