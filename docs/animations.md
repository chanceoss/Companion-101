# Animation configuration

Edit `desktop_pet/assets/sprites.json` and restart Biscuit. The desktop pet and panel portrait share the same animation library. Frame loading, playback, motion, random idle choices, and transitions are separate from activity selection and screen movement.

## Replace or expand an activity

Keep the activity's existing state name and replace its `frames` list. For example, replace `working` with:

```json
"working": {
  "frames": ["work-01.png", "work-02.png", "work-03.png"],
  "fps": 8,
  "playback": "pingpong",
  "eyes": [],
  "transition": {"duration": 0.2, "easing": "smoothstep"},
  "motion": {
    "bob": {"wave": "sine", "amplitude": 0.7, "frequency": "cycle"}
  }
}
```

Put those transparent PNGs in the assets directory with matching canvas size and character alignment. A frame can instead reference an atlas cell: `{"atlas": "activities", "column": 1, "row": 0}`. Existing atlas declarations and normalized row/column edges remain supported. Files are loaded and cached at startup; animation does not read them from disk each frame. No animation-engine code changes are needed.

Atlas `row_edges` and `column_edges` are normalized source-image coordinates that define the full crop for each pose. Optional `column_anchors` supplies one horizontal body anchor per column, also measured against the full source-image width. Each anchor must lie strictly inside its column's edges. The expressions atlas uses custom crop edges and `"column_anchors": [0.125, 0.375, 0.625, 0.875]` to keep Biscuit's torso centered while the tail changes the silhouette's bounds. Atlases without anchors retain the default bottom-center alignment.

The existing activity mappings are Explore → `exploring`, Work → `working`, Hi → `greeting`, Nap → `sleeping`, Follow → `following`. Movement uses `walking`; affection uses `happy`; dragging uses `dragged`; show/hide use `entering`/`leaving`. Keep these states when replacing bundled artwork. Adding a new UI activity or a new desktop action still requires application code.

The six original reactions map directly to `sitting`, `stretching`, `yawning`, `dancing`, `hopping`, and `tail_wag`. Their artwork is in `expressions.png`, a four-column, six-row atlas in that order. Each row supplies four poses; the configured sequences repeat cells for holds and repeated movements. Replace these frame lists to change a reaction without changing its menu action. `happy` shares the dance artwork for affection and celebrations.

`conversation-expressions.png` adds another four-column, six-row transparent atlas. Its rows are `thinking`, `curious`, `laughing`, `surprised`, `comforting`, and `bashful`. Each has four distinct painted poses, a configured hold sequence, subtle motion, `eyes: []`, and a 0.34-second incoming blend. Source row/column edges are calibrated to the transparent gutters; explicit column anchors keep the body stable as paws and tail move. The existing loader preloads all 24 cells. PNG assets are included by the existing wheel/PyInstaller asset rules.

The internal `chat_thinking` clip reuses the thinking row in a looping ping-pong sequence. The chat lifecycle owns it: response, cancellation, clear, and disabling automatic reactions end the loop. It is excluded from the manual menu and random idle choices. The manual `thinking` reaction is still a one-shot and returns to the current activity. There are no new animation-engine branches or background polling timers.

`conversation.py` selects an allowlisted reaction from local text/phrase rules, ignoring fenced/inline code and quoted lines. The user's worry/sadness takes priority over a cheerful assistant reply. These modest rules are not a sentiment model; adjust them there to change the mapping. Text is processed in memory only, and no reaction metadata, conversation text, or extra request is sent to an AI provider. Preferences → General → **React during conversations** disables automatic reactions while keeping manual menu actions.

Run `python -m scripts.render_expression_preview --conversation` to export `docs/conversation-expressions.gif` and a static PNG from the real native painter. The original preview command still exports the six classic reactions.

## Clip settings

| Field | Meaning |
| --- | --- |
| `frames` | Nonempty ordered list of PNG paths or atlas cells. Paths stay inside the assets directory. |
| `fps` | Frames per second, greater than zero and at most 60; default 8. |
| `playback` | `loop` (default), `once`, or `pingpong`. Ping-pong traverses forward and backward without duplicating the endpoints. |
| `duration` | Optional clip length in seconds. Defaults to frame count / fps; ping-pong uses `(2 × count − 2) / fps` for multiple frames. |
| `next` | Optional destination state after a `once` clip finishes. Without it, the final frame and final progress pose hold. Ignored for looping clips. |
| `transition` | Incoming blend duration in seconds and `linear` or `smoothstep` easing. Defaults to the top-level `transitions` setting. Use duration 0 to cut. |
| `blink` | `auto` (default), `open`, or `closed`. |
| `eyes` | Optional normalized eyelid rectangles. Use `[]` for artwork with painted expressions or different eye positions. |
| `directions` | Optional `side` and `back` frame lists with the same count as the default/front list. |
| `mirror_left` | Mirror side-facing frames for leftward movement when true. |
| `label` | Optional friendly state label in the panel. |

An explicit duration controls completion and normalized motion; it does not retime fps. A long one-shot holds its last frame until that duration ends; a short one-shot can finish before all frames are displayed. Omit duration to play every frame exactly once at its configured fps.

`greeting` duration also controls how long the Hi activity temporarily overlays the current activity. `leaving` should be a one-shot with no `next`: its completion hides the window. `entering` and `happy` normally return to `idle`; the application then resumes any persistent activity.

The reaction states are also one-shots with `next: "idle"`. When triggered from a menu, the application restores the selected activity when the clip finishes. Work's timer continues, and Explore or Follow movement resumes afterward. The panel portrait follows the same reaction. Reaction titles and menu membership live in `gestures.py`; their frames, timing, expressions, and motion live in the manifest.

## Motion channels

Each state's optional `motion` object supports `x` (horizontal displacement in pet design pixels; positive goes right), `bob` (vertical displacement; negative goes up), `rotation` (degrees), `sx`/`sy` (scale), and `opacity` (clamped to 0–1). Displacements scale with the displayed pet size. Missing channels default to 0 displacement/rotation and 1 scale/opacity. A channel accepts a constant number or one of these objects:

```json
{
  "x": {"wave": "sine", "amplitude": 6, "frequency": 1.75},
  "bob": {"wave": "abs_sine", "amplitude": -2, "offset": 0, "frequency": "cycle"},
  "rotation": {"wave": "sine", "amplitude": 3, "frequency": 0.5, "phase": 0},
  "opacity": {"wave": "progress", "from": 0, "to": 1, "easing": "smoothstep"},
  "sy": {"wave": "keyframes", "keys": [[0, 1], [0.4, 1.05], [1, 1]], "easing": "smoothstep"}
}
```

Sine frequency is in cycles per second, or `"cycle"` to synchronize one oscillation to a clip's duration. Phase is in radians. Offset defaults to 1 for scale/opacity and 0 for displacement/rotation. Progress and keyframe timing use normalized clip time from 0 to 1, repeating for loops and clamping for one-shots. Keyframe times must strictly increase from 0 to 1. Easing is `linear` (default for motion) or `smoothstep`.

The dance uses `x` for side-to-side motion. Hops combine vertical keyframes with widening before takeoff, stretching in the air, and a short landing squash. Facial expressions and tail positions are drawn into the frames; use `eyes: []` so procedural eyelids do not cover those expressions.

## Smooth transitions

Incoming transitions blend sprite frames and interpolate the currently rendered pose toward the destination pose. The destination frame sequence continues at its configured fps. Interrupting a blend retains its current source frames, their weights, and the visible pose, then eases toward the new destination. Rapid activity changes therefore continue from what is already on screen.

The desktop pet and portrait use the same `rendering.py` painter. It combines weighted sprite pixels on a transparent surface before applying the pose, keeping overlapping artwork from dimming halfway through a blend. Outgoing walking views retain their facing direction during the transition. Set a common default at the top level:

```json
"transitions": {"duration": 0.32, "easing": "smoothstep"},
"blink": {"interval": [2.5, 6], "duration": 0.16}
```

The bundled states use incoming durations between 0.22 and 0.6 seconds where appropriate. Sitting, stretching, and yawning ease in more slowly than hops. Per-state `transition` overrides the common default. Entering and leaving use their own opacity and motion curves.

## Random idle variants

The bundled pet chooses among the six reactions and looking around every 6–13 seconds of resting. Add another clip to `states`, then add its name and relative weight to `idle_behavior`. A variant must play once and return to the configured base state:

```json
"idle_behavior": {
  "base": "idle",
  "interval": [6, 13],
  "variants": ["sitting", "stretching", "yawning", "dancing", "hopping", "tail_wag", "idle_look"],
  "weights": [3, 2, 1, 1, 1, 3, 2]
}
```

Weights are positive numbers matching the variant list; omit them for equal probability. The delay starts again on returning to the base. Idle variants stop being scheduled during other activities, walking, dragging, and show/hide. They never change the selected companion activity. Remove `idle_behavior` to disable them. Use `idle` as the base for the existing app's rest behavior.

The library validates playback modes, timing, references, motion channels, keyframes, and idle variants at startup. To check changes, run `.venv/bin/python -m pytest -q` and `.venv/bin/python run_pet.py --smoke-test` (use `.venv\Scripts\python` on Windows). The preview scripts listed in the README render with this same configuration.
