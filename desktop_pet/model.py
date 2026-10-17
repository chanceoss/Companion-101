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
            breath = math.sin(t * 1.7)
            return Pose(1, 0, 1 + breath * .007, 1 + breath * .014, blink=True)
        if self.state == "working":
            return Pose(math.sin(t * 5) * .65, 0, 1, 1 + math.sin(t * 2) * .003)
        if self.state == "greeting":
            wave = math.sin(t * 9)
            return Pose(-abs(wave) * 4, wave * 2.5, 1 + wave * .008, 1 - wave * .008)
        if self.state in ("exploring", "following"):
            return Pose(math.sin(t * 2) * 1.2, math.sin(t) * .8)
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
