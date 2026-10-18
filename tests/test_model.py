import math
import pytest
from desktop_pet.model import Animator, WalkMotion, clamp_position, offline_reply


def test_entry_and_affection_finish_and_restore_idle():
    animation = Animator()
    assert animation.advance(0).opacity == 0
    animation.advance(.7)
    assert animation.state == "idle"
    animation.set_state("happy")
    assert animation.advance(.1).bob < 0
    animation.advance(1.5)
    assert animation.state == "idle"


@pytest.mark.parametrize("state", ["idle", "walking", "happy", "sleeping", "dragged", "entering", "leaving", "exploring", "working", "greeting", "following"])
def test_animation_remains_finite_and_visible(state):
    animation = Animator()
    animation.set_state(state)
    for _ in range(60):
        pose = animation.advance(1 / 30)
        assert 0 <= pose.opacity <= 1
        assert .7 <= pose.sx <= 1.2
        assert .7 <= pose.sy <= 1.2
        assert math.isfinite(pose.bob)


def test_negative_monitor_origin_and_small_screen():
    assert clamp_position(-2200, -100, -1920, 0, 0, 1080, 290, 310) == (-1920, 0)
    assert clamp_position(50, 1000, -1920, 0, 0, 1080, 290, 310) == (-290, 770)
    assert clamp_position(200, 200, 0, 0, 100, 100, 290, 310) == (0, 0)


def test_offline_companion_is_honest_about_capability():
    assert "Biscuit" in offline_reply("hello")
    assert "offline mode" in offline_reply("tell me about quantum mechanics").lower()
    assert "slow breath" in offline_reply("I am stressed")


@pytest.mark.parametrize("vector,facing,mirror", [
    ((1, 0), "side", False), ((-1, 0), "side", True),
    ((0, 1), "front", False), ((0, -1), "back", False),
    ((2, 1), "side", False), ((-1, -2), "back", False),
])
def test_walk_faces_actual_travel_direction(vector, facing, mirror):
    motion = WalkMotion(0, 0, *vector)
    assert motion.facing == facing
    assert motion.mirrored == mirror
    assert math.hypot(motion.vx, motion.vy) == pytest.approx(1)


def test_diagonal_speed_and_subpixel_distance_match_horizontal():
    straight, diagonal = WalkMotion(100, 100, 1, 0), WalkMotion(100, 100, 1, 1)
    for _ in range(100):
        for motion in (straight, diagonal):
            motion.step(.01, (0, 0, 1000, 1000), 100, 100)
    for motion in (straight, diagonal):
        assert math.hypot(motion.x - 100, motion.y - 100) == pytest.approx(42)


def test_walk_bounces_on_both_axes_and_changes_view():
    motion = WalkMotion(699, 599, 1, 1)
    assert motion.step(.1, (0, 0, 1000, 900), 300, 300) == (700, 600)
    assert motion.vx < 0 and motion.vy < 0
    up = WalkMotion(-1900, 1, 0, -1)
    assert up.facing == "back"
    assert up.step(.1, (-1920, 0, 0, 1080), 290, 310) == (-1900, 0)
    assert up.facing == "front"


def test_walk_stays_in_bounds_on_negative_and_small_monitors():
    motion = WalkMotion(-1919, 1, -1, -1)
    for _ in range(300):
        x, y = motion.step(.1, (-1920, 0, 0, 1080), 290, 310)
        assert -1920 <= x <= -290
        assert 0 <= y <= 770
    assert motion.step(.1, (0, 0, 100, 100), 290, 310) == (0, 0)


def test_secondary_walk_motion_repeats_with_sprite_loop():
    a, b = Animator(walk_fps=8, walk_frames=4), Animator(walk_fps=8, walk_frames=4)
    a.set_state("walking")
    b.set_state("walking")
    a.advance(1)
    b.advance(1)
    first, second = a.advance(.07), b.advance(.57)
    assert first.bob == pytest.approx(second.bob)
    assert first.rotation == pytest.approx(second.rotation)
    assert abs(first.rotation) < 1.3
