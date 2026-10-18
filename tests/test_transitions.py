"""Visible continuity when users interrupt clips or clips finish mid-transition."""
from dataclasses import fields

import pytest

from desktop_pet.animations import AnimationLibrary, Animator, Pose


def library():
    return AnimationLibrary({
        "transitions": {"duration": 1, "easing": "linear"},
        "states": {
            "idle": {"frames": ["idle.png"], "motion": {"x": 0, "bob": 0}},
            "sit": {"frames": ["sit.png"], "motion": {"x": 12, "bob": 10}},
            "dance": {"frames": ["a.png", "b.png", "c.png"], "fps": 10,
                      "motion": {"x": -16, "bob": -20, "rotation": 8}},
        },
    })


def assert_pose_equal(actual, expected):
    for field in fields(Pose):
        assert getattr(actual, field.name) == pytest.approx(getattr(expected, field.name))


def assert_layers_equal(actual, expected):
    assert [layer[0] for layer in actual] == [layer[0] for layer in expected]
    assert [layer[1] for layer in actual] == pytest.approx([layer[1] for layer in expected])
    assert [layer[2] for layer in actual] == pytest.approx([layer[2] for layer in expected])


def test_rapid_activity_changes_preserve_every_visible_frame_and_pose():
    animator = Animator(library=library())
    animator.set_state("sit")
    first_pose = animator.advance(.25)
    first_layers = animator.layers()
    assert_layers_equal(first_layers, [("idle", 0, .75), ("sit", .25, .25)])

    animator.set_state("dance")
    assert_pose_equal(animator.advance(0), first_pose)
    assert_layers_equal(animator.layers(), first_layers)

    second_pose = animator.advance(.25)
    second_layers = animator.layers()
    assert_layers_equal(second_layers, [
        ("idle", 0, .5625), ("sit", .25, .1875), ("dance", .25, .25),
    ])
    animator.set_state("idle")
    assert_pose_equal(animator.advance(0), second_pose)
    assert_layers_equal(animator.layers(), second_layers)
    animator.advance(1)
    assert animator.layers() == [("idle", 1, 1)]


def test_restarting_a_clip_keeps_its_previous_frame_until_the_blend_advances():
    animator = Animator(library=library())
    animator.set_state("dance", transition=False)
    animator.advance(.2)
    animator.set_state("dance", restart=True)
    assert animator.layers() == [("dance", .2, 1)]
    animator.advance(.1)
    assert_layers_equal(animator.layers(), [("dance", .2, .9), ("dance", .1, .1)])
    animator.advance(.1)
    # Both sources now refer to the same frame time, so they merge cleanly.
    assert animator.layers() == [("dance", .2, 1)]


def test_short_clip_completion_captures_the_actual_transition_boundary():
    config = library().manifest
    config["states"]["sit"].update(playback="once", duration=.1, next="dance")
    animator = Animator(library=AnimationLibrary(config))
    animator.set_state("sit")
    pose = animator.advance(.1)
    assert animator.state == "dance"
    assert animator.elapsed == 0
    # The sit clip finished while still 90% faded into the original idle.
    # Its full terminal pose must not replace the actual blended pose.
    assert pose.x == pytest.approx(1.2)
    assert pose.bob == pytest.approx(1)
    assert_layers_equal(animator.layers(), [("idle", 0, .9), ("sit", .1, .1)])
    assert_pose_equal(animator.advance(0), pose)


def test_large_elapsed_step_matches_updates_split_at_chained_clip_boundaries():
    config = library().manifest
    config["states"]["sit"].update(playback="once", duration=.1, next="dance")
    config["states"]["dance"].update(playback="once", duration=.15, next="idle")
    a, b = (Animator(library=AnimationLibrary(config)) for _ in range(2))
    for animator in (a, b):
        animator.set_state("sit")
    large_step_pose = a.advance(.32)
    for dt in (.1, .15, .07):
        split_step_pose = b.advance(dt)
    assert a.state == b.state == "idle"
    assert a.clock == pytest.approx(.32)
    assert a.elapsed == pytest.approx(.07)
    assert_pose_equal(large_step_pose, split_step_pose)
    assert_layers_equal(a.layers(), b.layers())


def test_one_shot_can_restart_itself_through_configured_next_state():
    config = library().manifest
    config["states"]["sit"].update(playback="once", duration=.1, next="sit")
    animator = Animator(library=AnimationLibrary(config))
    animator.set_state("sit")
    animator.advance(.35)
    assert animator.state == "sit"
    assert animator.clock == pytest.approx(.35)
    assert animator.elapsed == pytest.approx(.05)
    assert sum(layer[2] for layer in animator.layers()) == pytest.approx(1)


def test_repeated_interruptions_keep_normalized_sources_and_drop_old_remnants():
    animator = Animator(library=library())
    for i in range(160):
        animator.set_state("sit" if i % 2 == 0 else "dance")
        animator.advance(.4)
        assert sum(layer[2] for layer in animator.layers()) == pytest.approx(1)
        assert all(layer[2] > 1e-8 for layer in animator.layers())
    # Old snapshots decay instead of accumulating indefinitely.
    assert len(animator.layers()) < 40
    animator.advance(1)
    assert len(animator.layers()) == 1


def test_horizontal_motion_channel_samples_and_blends_without_mutating_config():
    config = library().manifest
    config["states"]["sit"].update(playback="once", duration=1, motion={
        "x": {"wave": "keyframes", "keys": [[0, 0], [.5, 18], [1, 0]]},
    })
    clips = AnimationLibrary(config)
    assert clips.sample("idle", 0, False).x == 0
    assert clips.sample("sit", .25, False).x == pytest.approx(9)
    assert clips.sample("sit", .5, False).x == pytest.approx(18)
    assert clips.sample("sit", .25, False).x == pytest.approx(9)
    assert config["states"]["sit"]["motion"]["x"]["keys"][1] == [.5, 18]
    animator = Animator(library=clips)
    animator.set_state("sit")
    assert animator.advance(.5).x == pytest.approx(9)
    config["states"]["sit"]["motion"]["unsupported"] = 1
    with pytest.raises(ValueError, match="Unknown motion channel unsupported"):
        AnimationLibrary(config)
