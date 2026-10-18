"""Data-driven animation clips, idle choices, playback, and transitions (no Qt)."""
from copy import deepcopy
from dataclasses import dataclass, fields
from functools import lru_cache
import json
import math
from pathlib import Path
import random


@dataclass(frozen=True)
class Pose:
    bob: float = 0
    rotation: float = 0
    sx: float = 1
    sy: float = 1
    opacity: float = 1
    blink: bool = False


def number(value, label, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return value


def interval(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} needs a [minimum, maximum] interval.")
    low, high = (number(v, label, .001) for v in value)
    if low > high:
        raise ValueError(f"{label} minimum cannot exceed its maximum.")
    return low, high


def eased(progress, name):
    value = min(1, max(0, progress))
    return value * value * (3 - 2 * value) if name == "smoothstep" else value


class AnimationLibrary:
    """All clip behavior is supplied by sprites.json; adding a clip needs no code."""
    def __init__(self, manifest):
        if not isinstance(manifest, dict) or not isinstance(manifest.get("states"), dict):
            raise ValueError("Animation manifest needs a states object.")
        self.manifest = deepcopy(manifest)
        self.states = self.manifest.get("states", {})
        if "idle" not in self.states:
            raise ValueError("Animation states must include idle.")
        self.transition = self.manifest.get("transitions", {"duration": 0, "easing": "smoothstep"})
        self._validate_transition(self.transition)
        self.blink = self.manifest.get("blink", {"interval": [2.5, 6], "duration": .16})
        if not isinstance(self.blink, dict) or "interval" not in self.blink or "duration" not in self.blink:
            raise ValueError("Blink settings need interval and duration.")
        interval(self.blink["interval"], "Blink interval")
        number(self.blink["duration"], "Blink duration", .001)
        for name, spec in self.states.items():
            if not isinstance(spec, dict):
                raise ValueError(f"Animation {name} must be an object.")
            if not isinstance(spec.get("frames"), list) or not spec["frames"]:
                raise ValueError(f"Animation {name} needs a nonempty frame list.")
            fps = number(spec.get("fps", 8), f"{name} fps", .001)
            spec.setdefault("fps", fps)
            if fps > 60:
                raise ValueError(f"{name} fps cannot exceed 60.")
            if spec.get("playback", "loop") not in ("loop", "once", "pingpong"):
                raise ValueError(f"Unknown playback mode in {name}.")
            if "duration" in spec:
                number(spec["duration"], f"{name} duration", .001)
            if spec.get("next") is not None and (not isinstance(spec["next"], str) or spec["next"] not in self.states):
                raise ValueError(f"Unknown next animation in {name}: {spec['next']}.")
            self._validate_transition(spec.get("transition", self.transition))
            if spec.get("blink", "auto") not in ("auto", "open", "closed"):
                raise ValueError(f"Unknown blink mode in {name}.")
            if not isinstance(spec.get("motion", {}), dict):
                raise ValueError(f"Motion in {name} must be an object.")
            for channel, config in spec.get("motion", {}).items():
                if channel not in ("bob", "rotation", "sx", "sy", "opacity"):
                    raise ValueError(f"Unknown motion channel {channel} in {name}.")
                if isinstance(config, (int, float)):
                    number(config, f"{name}.{channel}")
                    continue
                if not isinstance(config, dict):
                    raise ValueError(f"Motion channel {name}.{channel} must be a number or object.")
                if config.get("wave", "sine") not in ("sine", "abs_sine", "progress", "keyframes"):
                    raise ValueError(f"Unknown motion wave in {name}.{channel}.")
                if config.get("easing", "linear") not in ("linear", "smoothstep"):
                    raise ValueError(f"Unknown motion easing in {name}.{channel}.")
                for key in ("offset", "amplitude", "phase", "from", "to"):
                    if key in config:
                        number(config[key], f"{name}.{channel}.{key}")
                if config.get("frequency", "cycle") != "cycle":
                    number(config["frequency"], f"{name}.{channel}.frequency", 0)
                if config.get("wave") == "keyframes":
                    keys = config.get("keys", [])
                    if len(keys) < 2 or any(not isinstance(k, list) or len(k) != 2 for k in keys):
                        raise ValueError(f"{name}.{channel} needs at least two [time, value] keys.")
                    for t, value in keys:
                        number(t, "Keyframe time", 0)
                        number(value, "Keyframe value")
                    if keys[0][0] != 0 or keys[-1][0] != 1 or any(a[0] >= b[0] for a, b in zip(keys, keys[1:])):
                        raise ValueError(f"{name}.{channel} keyframe times must increase from 0 to 1.")
        self.idle = self.manifest.get("idle_behavior")
        if self.idle:
            if not isinstance(self.idle, dict):
                raise ValueError("Idle behavior must be an object.")
            base, variants = self.idle.get("base", "idle"), self.idle.get("variants", [])
            if (not isinstance(base, str) or base not in self.states or not isinstance(variants, list)
                    or not variants or any(not isinstance(v, str) or v not in self.states or v == base for v in variants)):
                raise ValueError("Idle variants must name existing animations distinct from the base.")
            interval(self.idle.get("interval", []), "Idle interval")
            weights = self.idle.get("weights", [1] * len(variants))
            if len(weights) != len(variants):
                raise ValueError("Idle weights must match idle variants.")
            for weight in weights:
                number(weight, "Idle weight", .001)
            for variant in variants:
                spec = self.states[variant]
                if spec.get("playback") != "once" or spec.get("next") != base:
                    raise ValueError("Idle variants must play once and return to the base animation.")

    @staticmethod
    def _validate_transition(config):
        if not isinstance(config, dict):
            raise ValueError("Transition settings must be an object.")
        number(config.get("duration", 0), "Transition duration", 0)
        if config.get("easing", "smoothstep") not in ("linear", "smoothstep"):
            raise ValueError("Unknown transition easing.")

    def duration(self, state):
        spec = self.states[state]
        count = len(spec["frames"])
        if spec.get("playback") == "pingpong" and count > 1:
            count = count * 2 - 2
        return spec.get("duration", count / spec.get("fps", 8))

    def frame_index(self, state, elapsed, count=None):
        spec = self.states[state]
        count = count or len(spec["frames"])
        index = int(max(0, elapsed) * spec.get("fps", 8))
        playback = spec.get("playback", "loop")
        if playback == "once":
            return min(count - 1, index)
        if playback == "pingpong" and count > 1:
            index %= count * 2 - 2
            return index if index < count else count * 2 - 2 - index
        return index % count

    def sample(self, state, elapsed, blink):
        spec = self.states[state]
        duration = self.duration(state)
        once = spec.get("playback") == "once"
        progress = min(1, max(0, elapsed / duration)) if once else elapsed / duration % 1
        values = {}
        for channel, config in spec.get("motion", {}).items():
            if isinstance(config, (int, float)):
                values[channel] = config
                continue
            wave = config.get("wave", "sine")
            if wave == "progress":
                f = eased(progress, config.get("easing", "linear"))
                values[channel] = config.get("from", 0) + (config.get("to", 0) - config.get("from", 0)) * f
            elif wave == "keyframes":
                keys = config["keys"]
                for (a, av), (b, bv) in zip(keys, keys[1:]):
                    if a <= progress <= b:
                        f = eased((progress - a) / (b - a), config.get("easing", "linear"))
                        values[channel] = av + (bv - av) * f
                        break
            else:
                frequency = config.get("frequency", "cycle")
                if frequency == "cycle":
                    frequency = 1 / duration
                value = math.sin(math.tau * frequency * elapsed + config.get("phase", 0))
                if wave == "abs_sine":
                    value = abs(value)
                default = 1 if channel in ("sx", "sy", "opacity") else 0
                values[channel] = config.get("offset", default) + value * config.get("amplitude", 0)
        mode = spec.get("blink", "auto")
        values["blink"] = blink if mode == "auto" else mode == "closed"
        values["opacity"] = min(1, max(0, values.get("opacity", 1)))
        return Pose(**values)


@lru_cache(maxsize=1)
def default_library():
    path = Path(__file__).resolve().parent / "assets" / "sprites.json"
    return AnimationLibrary(json.loads(path.read_text(encoding="utf-8")))


class Animator:
    def __init__(self, walk_fps=None, walk_frames=None, *, library=None, rng=None):
        self.library = library or default_library()
        # Backwards-compatible timing overrides for callers constructing a preview.
        if walk_fps is not None or walk_frames is not None:
            manifest = deepcopy(self.library.manifest)
            walking = manifest["states"]["walking"]
            if walk_fps is not None:
                walking["fps"] = walk_fps
            if walk_frames is not None:
                walking["frames"] = [walking["frames"][0]] * max(1, walk_frames)
            self.library = AnimationLibrary(manifest)
        self.rng = rng or random.Random()
        self.state = "entering" if "entering" in self.library.states else "idle"
        self.elapsed = self.clock = 0.0
        self.blink_at = self.rng.uniform(*self.library.blink["interval"])
        self._idle_at = math.inf
        self._previous = None
        self._transition_start = 0.0
        self._transition_duration = 0.0
        self._transition_easing = "smoothstep"
        self._pose = self.library.sample(self.state, 0, False)
        self._from_pose = self._pose
        self._schedule_idle()

    def _schedule_idle(self):
        idle = self.library.idle
        if idle and self.state == idle.get("base", "idle"):
            self._idle_at = self.clock + self.rng.uniform(*idle["interval"])
        else:
            self._idle_at = math.inf

    def set_state(self, state, restart=False, *, transition=True):
        if state not in self.library.states:
            raise ValueError(f"Unknown animation: {state}")
        if state == self.state and not restart:
            return
        self._previous = self.state, self.elapsed
        self._from_pose = self._pose
        self.state, self.elapsed = state, 0.0
        config = self.library.states[state].get("transition", self.library.transition)
        self._transition_duration = config.get("duration", 0) if transition else 0
        self._transition_easing = config.get("easing", "smoothstep")
        self._transition_start = self.clock
        self._schedule_idle()

    @property
    def finished(self):
        return (self.library.states[self.state].get("playback") == "once"
                and self.elapsed >= self.library.duration(self.state))

    @property
    def blend(self):
        if not self._previous or not self._transition_duration:
            return 1.0
        return eased((self.clock - self._transition_start) / self._transition_duration, self._transition_easing)

    def layers(self):
        weight = self.blend
        if self._previous and weight < 1:
            state, elapsed = self._previous
            return [(state, elapsed, 1 - weight), (self.state, self.elapsed, weight)]
        return [(self.state, self.elapsed, 1)]

    def advance(self, dt):
        dt = max(0, number(dt, "Animation elapsed time"))
        self.clock += dt
        self.elapsed += dt
        if self.clock > self.blink_at + self.library.blink["duration"]:
            self.blink_at = self.clock + self.rng.uniform(*self.library.blink["interval"])
        # A limited chain prevents a pathological custom graph from hanging startup.
        for _ in range(32):
            spec = self.library.states[self.state]
            if not self.finished or spec.get("next") is None:
                break
            remaining = self.elapsed - self.library.duration(self.state)
            self._pose = self.library.sample(self.state, self.library.duration(self.state), False)
            self.set_state(spec["next"])
            self.elapsed = remaining
            self._transition_start -= remaining
            self._idle_at -= remaining
        if self.clock >= self._idle_at:
            idle = self.library.idle
            variant = self.rng.choices(idle["variants"], weights=idle.get("weights"), k=1)[0]
            self.set_state(variant)
        blinking = self.blink_at <= self.clock <= self.blink_at + self.library.blink["duration"]
        target = self.library.sample(self.state, self.elapsed, blinking)
        weight = self.blend
        values = {f.name: getattr(self._from_pose, f.name) * (1 - weight) + getattr(target, f.name) * weight
                  for f in fields(Pose) if f.name != "blink"}
        self._pose = Pose(**values, blink=target.blink)
        return self._pose
