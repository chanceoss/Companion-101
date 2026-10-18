import json
import random
import pytest
from desktop_pet.animations import AnimationLibrary, Animator
from desktop_pet.sprites import ASSETS, SpriteBank
from desktop_pet.pet import PetWindow
from desktop_pet.storage import Settings


def manifest():
    return {
        "transitions": {"duration": .2, "easing": "linear"},
        "states": {
            "idle": {"frames": ["idle.png"], "fps": 8},
            "dance": {"frames": ["a.png", "b.png", "c.png"], "fps": 10,
                      "playback": "once", "next": "idle", "motion": {"bob": 20}},
        },
    }


def test_new_multiframe_clip_completes_and_returns_without_engine_changes():
    library = AnimationLibrary(manifest())
    animator = Animator(library=library)
    animator.set_state("dance", transition=False)
    assert library.frame_index(animator.state, 0) == 0
    animator.advance(.1)
    assert library.frame_index(animator.state, animator.elapsed) == 1
    animator.advance(.11)
    assert library.frame_index(animator.state, animator.elapsed) == 2
    animator.advance(.1)
    assert animator.state == "idle"
    assert library.frame_index("dance", 100) == 2


def test_loop_pingpong_and_one_shot_hold_correct_frames():
    config = manifest()
    for playback, expected in (("loop", [0, 1, 2, 0, 1]),
                               ("pingpong", [0, 1, 2, 1, 0]),
                               ("once", [0, 1, 2, 2, 2])):
        config["states"]["dance"]["playback"] = playback
        library = AnimationLibrary(config)
        assert [library.frame_index("dance", t) for t in (0, .1, .2, .31, .41)] == expected


def test_transitions_blend_pose_and_frames_and_can_be_interrupted():
    config = manifest()
    config["states"]["other"] = {"frames": ["other.png"], "fps": 8, "motion": {"bob": 80}}
    animator = Animator(library=AnimationLibrary(config))
    animator.set_state("dance")
    assert animator.advance(0).bob == 0
    assert animator.advance(.1).bob == pytest.approx(10)
    assert [layer[2] for layer in animator.layers()] == pytest.approx([.5, .5])
    animator.set_state("other")
    assert animator.advance(0).bob == pytest.approx(10)
    assert animator.advance(.2).bob == pytest.approx(80)
    assert animator.layers() == [("other", .2, 1)]


def test_keyframed_motion_is_configurable_and_clamped_at_completion():
    config = manifest()
    config["states"]["dance"].update(duration=1, next=None, motion={"rotation": {
        "wave": "keyframes", "keys": [[0, 0], [.5, 12], [1, -2]], "easing": "linear"}})
    animator = Animator(library=AnimationLibrary(config))
    animator.set_state("dance", transition=False)
    assert animator.advance(.25).rotation == pytest.approx(6)
    assert animator.advance(.25).rotation == pytest.approx(12)
    assert animator.advance(10).rotation == pytest.approx(-2)
    assert animator.finished


def test_seeded_random_idle_variants_return_and_stop_during_other_activities():
    config = manifest()
    config["states"]["look"] = {"frames": ["look.png"], "fps": 8, "playback": "once", "duration": .1, "next": "idle"}
    config["states"]["stretch"] = {"frames": ["stretch.png"], "fps": 8, "playback": "once", "duration": .1, "next": "idle"}
    config["idle_behavior"] = {"base": "idle", "interval": [.2, .2], "variants": ["look", "stretch"], "weights": [2, 1]}
    animator = Animator(library=AnimationLibrary(config), rng=random.Random(7))
    seen = set()
    for _ in range(30):
        animator.advance(.21)
        seen.add(animator.state)
        assert animator.state in ("look", "stretch")
        animator.advance(.11)
        assert animator.state == "idle"
    assert seen == {"look", "stretch"}
    animator.set_state("dance")
    animator.advance(.21)
    assert animator.state == "dance"


@pytest.mark.parametrize("change", [
    lambda c: c["states"]["dance"].update(next="missing"),
    lambda c: c["states"]["dance"].update(playback="missing"),
    lambda c: c["states"]["dance"].update(duration=0),
    lambda c: c["states"]["dance"].update(fps=float("nan")),
    lambda c: c.update(transitions={"duration": -1}),
    lambda c: c.update(transitions=[]),
    lambda c: c["states"]["dance"].update(motion={"bob": {"wave": "unknown"}}),
    lambda c: c["states"]["dance"].update(motion={"bob": {"wave": "keyframes", "keys": [[0, 0], [.8, 2], [.5, 3], [1, 0]]}}),
    lambda c: c.update(idle_behavior={"variants": ["missing"], "interval": [1, 2]}),
])
def test_invalid_animation_configuration_is_reported(change):
    config = manifest()
    change(config)
    with pytest.raises(ValueError):
        AnimationLibrary(config)


def test_activity_frames_and_exit_duration_are_read_from_manifest(app, tmp_path):
    config = json.loads((ASSETS / "sprites.json").read_text())
    config["states"]["working"].update(frames=config["states"]["walking"]["frames"][:3], fps=5, playback="once")
    config["states"]["leaving"]["duration"] = .9
    for path in ASSETS.glob("*.png"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / "sprites.json").write_text(json.dumps(config))
    sprites = SpriteBank(tmp_path)
    assert len({sprites.frame("working", t).cacheKey() for t in (0, .21, .41)}) == 3
    assert sprites.frame("working", 10).cacheKey() == sprites.frame("working", .41).cacheKey()
    pet = PetWindow(Settings(tmp_path / "settings"), sprites)
    pet.timer.stop()
    pet.show()
    try:
        pet.hide_animated()
        pet.animator.advance(.65)
        pet.tick()
        assert pet.isVisible()
        pet.animator.advance(.3)
        pet.tick()
        assert not pet.isVisible()
    finally:
        pet.hide()
        pet.bubble.deleteLater()
        pet.deleteLater()
