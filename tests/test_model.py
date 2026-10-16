import math
import pytest
from desktop_pet.model import Animator, clamp_position, offline_reply


def test_entry_and_affection_finish_and_restore_idle():
    animation = Animator()
    assert animation.advance(0).opacity == 0
    animation.advance(.7)
    assert animation.state == "idle"
    animation.set_state("happy")
    assert animation.advance(.1).bob < 0
    animation.advance(1.5)
    assert animation.state == "idle"


@pytest.mark.parametrize("state", ["idle", "walking", "happy", "sleeping", "dragged", "entering", "leaving"])
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
