"""Pixel checks for expressive sprites and uninterrupted native crossfades."""
from dataclasses import replace
import hashlib

import pytest
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBitmap, QColor, QImage, QPainter, QPixmap, QRegion

from desktop_pet.animations import AnimationLibrary, Animator, Pose
from desktop_pet.gestures import GESTURE_STATES
from desktop_pet.model import WalkMotion
from desktop_pet.pet import PetWindow
from desktop_pet.rendering import draw_character
from desktop_pet.sprites import SpriteBank
from desktop_pet.storage import Settings


class SyntheticSprites:
    def __init__(self):
        self.animation_library = AnimationLibrary({
            "transitions": {"duration": 1, "easing": "linear"},
            "states": {state: {"frames": [f"{state}.png"], "mirror_left": state == "walking"}
                       for state in ("idle", "blue", "green", "walking")},
        })
        self.images = {}
        for state, color in (("idle", "red"), ("blue", "blue"), ("green", "lime"), ("walking", "magenta")):
            image = QPixmap(480, 480)
            image.fill(QColor(color))
            self.images[state] = image
        side = QPixmap(480, 480)
        side.fill(QColor("red"))
        painter = QPainter(side)
        painter.fillRect(QRectF(240, 0, 240, 480), QColor("yellow"))
        painter.end()
        self.side = side
        self.calls = []

    def frame(self, state, elapsed, facing="front"):
        self.calls.append((state, elapsed, facing))
        return self.side if state == "walking" and facing == "side" else self.images[state]

    def spec(self, state):
        return self.animation_library.states[state]

    def eyes(self, state):
        return []


def render(sprites, animator, pose=None, *, size=(360, 360), origin=(180, 330), width=255,
           facing="front", direction=1):
    canvas = QImage(*size, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.translate(*origin)
    draw_character(painter, sprites, animator, pose or animator.advance(0), width,
                   facing=facing, direction=direction)
    painter.end()
    return canvas


def alpha_bounds(image):
    return QRegion(QBitmap.fromImage(image.createAlphaMask(Qt.ThresholdAlphaDither))).boundingRect()


def image_bytes(image):
    return bytes(image.constBits())


@pytest.mark.parametrize("progress", [.25, .5, .75])
def test_crossfade_blends_premultiplied_color_without_dimming_opaque_pixels(app, progress):
    sprites = SyntheticSprites()
    animator = Animator(library=sprites.animation_library)
    animator.set_state("blue")
    pose = animator.advance(progress)
    color = render(sprites, animator, pose).pixelColor(180, 180)
    assert color.alpha() == pytest.approx(255, abs=1)
    assert color.red() == pytest.approx(255 * (1 - progress), abs=1)
    assert color.green() == 0
    assert color.blue() == pytest.approx(255 * progress, abs=1)


def test_interrupting_sprite_crossfades_preserves_the_visible_pixels_at_zero_time(app):
    sprites = SyntheticSprites()
    animator = Animator(library=sprites.animation_library)
    animator.set_state("blue")
    animator.advance(.5)
    before = render(sprites, animator)
    animator.set_state("green")
    after = render(sprites, animator)
    assert image_bytes(after) == image_bytes(before)
    animator.advance(.2)
    midway = render(sprites, animator)
    color = midway.pixelColor(180, 180)
    # Each of three weighted 8-bit layers can lose one alpha level in Qt.
    assert color.alpha() == pytest.approx(255, abs=3)
    assert (color.red(), color.green(), color.blue()) == pytest.approx((102, 51, 102), abs=1)
    animator.set_state("idle")
    assert image_bytes(render(sprites, animator)) == image_bytes(midway)


def test_crossfade_preserves_premultiplied_alpha_for_translucent_sprite_edges(app):
    sprites = SyntheticSprites()
    sprites.images["idle"].fill(QColor(255, 0, 0, 128))
    sprites.images["blue"].fill(QColor(0, 0, 255, 64))
    animator = Animator(library=sprites.animation_library)
    animator.set_state("blue")
    animator.advance(.5)
    image = render(sprites, animator)
    color = image.pixelColor(180, 180)
    assert color.alpha() == pytest.approx(96, abs=1)
    # These are unpremultiplied pixelColor values. The source alpha contributes
    # twice as much red as blue, rather than averaging their straight RGB.
    assert color.red() == pytest.approx(170, abs=3)
    assert color.blue() == pytest.approx(85, abs=3)
    assert color.green() == 0


def test_outgoing_walk_keeps_its_captured_view_and_direction_until_it_fades(app, tmp_path):
    sprites = SyntheticSprites()
    settings = Settings(tmp_path)
    settings.update(wander=False)
    pet = PetWindow(settings, sprites)
    pet.timer.stop()
    try:
        pet.walk_motion = WalkMotion(0, 0, -1, 0)
        pet.direction = -1
        pet.set_state("walking", transition=False)
        pet.animator.advance(.3)
        pet.set_state("blue")
        key = ("walking", .3)
        assert pet.animator.render_views[key] == ("side", -1)
        pet.animator.render_views[("idle", 99)] = ("back", 1)
        # Current facing is intentionally different from the captured source.
        image = render(sprites, pet.animator, facing="front", direction=1)
        assert ("walking", .3, "side") in sprites.calls
        assert image.pixelColor(100, 180) == QColor("yellow")
        assert image.pixelColor(260, 180) == QColor("red")
        assert pet.animator.render_views == {key: ("side", -1)}
        pet.animator.advance(1)
        render(sprites, pet.animator)
        assert pet.animator.render_views == {}
    finally:
        pet.hide()
        pet.bubble.deleteLater()
        pet.deleteLater()


def test_horizontal_pose_offset_moves_the_rendered_character_in_design_pixels(app):
    sprites = SyntheticSprites()
    animator = Animator(library=sprites.animation_library)
    centered = alpha_bounds(render(sprites, animator, Pose()))
    offset = alpha_bounds(render(sprites, animator, replace(Pose(), x=20)))
    assert offset == centered.translated(20, 0)
    # The offset scales with the rendered width, like bob and the pet itself.
    small_centered = alpha_bounds(render(sprites, animator, Pose(), width=127.5))
    small_offset = alpha_bounds(render(sprites, animator, replace(Pose(), x=20), width=127.5))
    assert small_offset == small_centered.translated(10, 0)


@pytest.fixture(scope="module")
def real_sprites(app):
    return SpriteBank()


def test_expression_atlas_has_24_distinct_nonempty_frames_with_transparent_corners(real_sprites):
    atlas = real_sprites.atlases["expressions"]
    assert set(atlas) == {(column, row) for column in range(4) for row in range(6)}
    hashes = set()
    for image in atlas.values():
        image = image.toImage()
        bounds = alpha_bounds(image)
        assert bounds.width() > 100 and bounds.height() > 100
        assert bounds.left() > 0 and bounds.top() > 0
        assert bounds.right() < image.width() - 1 and bounds.bottom() < image.height() - 1
        for x, y in ((0, 0), (479, 0), (0, 479), (479, 479)):
            assert image.pixelColor(x, y).alpha() == 0
        hashes.add(hashlib.sha256(image_bytes(image)).digest())
    assert len(hashes) == 24


@pytest.mark.parametrize("scale", [60, 100, 150])
def test_all_gesture_art_and_motion_stay_inside_the_desktop_pet_canvas(real_sprites, scale):
    unit = scale / 100
    width, height = round(290 * unit), round(310 * unit)
    # Paint onto a larger surface so pixels outside the actual window remain
    # detectable rather than being silently clipped by QWidget's backing store.
    padding = 80
    sprites = real_sprites
    for state in GESTURE_STATES:
        animator = Animator(library=sprites.animation_library)
        animator.set_state(state, transition=False)
        duration = sprites.animation_library.duration(state)
        for index in range(32):
            animator.elapsed = duration * index / 32
            pose = animator.advance(0)
            image = render(sprites, animator, pose, size=(width + 2 * padding, height + 2 * padding),
                           origin=(padding + width / 2, padding + height - 20 * unit),
                           width=255 * unit)
            bounds = alpha_bounds(image)
            assert not bounds.isEmpty(), (state, scale, index)
            assert (bounds.left() >= padding and bounds.top() >= padding
                    and bounds.right() < padding + width and bounds.bottom() < padding + height), (
                state, scale, index, bounds,
            )
