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

The existing activity mappings are Explore → `exploring`, Work → `working`, Hi → `greeting`, Nap → `sleeping`, Follow → `following`. Movement uses `walking`; affection uses `happy`; dragging uses `dragged`; show/hide use `entering`/`leaving`. Keep these states when replacing bundled artwork. Adding a new UI activity or a new desktop action still requires application code.

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

## Motion channels

Each state's optional `motion` object supports `bob` (vertical displacement in pet design pixels; negative goes up), `rotation` (degrees), `sx`/`sy` (scale), and `opacity` (clamped to 0–1). Missing channels default to 0 displacement/rotation and 1 scale/opacity. A channel accepts a constant number or one of these objects:

```json
{
  "bob": {"wave": "abs_sine", "amplitude": -2, "offset": 0, "frequency": "cycle"},
  "rotation": {"wave": "sine", "amplitude": 3, "frequency": 0.5, "phase": 0},
  "opacity": {"wave": "progress", "from": 0, "to": 1, "easing": "smoothstep"},
  "sy": {"wave": "keyframes", "keys": [[0, 1], [0.4, 1.05], [1, 1]], "easing": "smoothstep"}
}
```

Sine frequency is in cycles per second, or `"cycle"` to synchronize one oscillation to a clip's duration. Phase is in radians. Offset defaults to 1 for scale/opacity and 0 for bob/rotation. Progress and keyframe timing use normalized clip time from 0 to 1, repeating for loops and clamping for one-shots. Keyframe times must strictly increase from 0 to 1. Easing is `linear` (default for motion) or `smoothstep`.

Incoming transitions crossfade sprite frames and interpolate the currently rendered pose toward the destination pose. The frame sequences continue at their configured fps. The engine supports interrupting a transition while retaining pose continuity. Set a common default at the top level:

```json
"transitions": {"duration": 0.16, "easing": "smoothstep"},
"blink": {"interval": [2.5, 6], "duration": 0.16}
```

## Random idle variants

The bundled pet randomly looks around or stretches every 7–14 seconds of resting. Add another clip to `states`, then add its name and relative weight to `idle_behavior`. A variant must play once and return to the configured base state:

```json
"idle_behavior": {
  "base": "idle",
  "interval": [7, 14],
  "variants": ["idle_look", "idle_stretch"],
  "weights": [2, 1]
}
```

Weights are positive numbers matching the variant list; omit them for equal probability. The delay starts again on returning to the base. Idle variants stop being scheduled during other activities, walking, dragging, and show/hide. They never change the selected companion activity. Remove `idle_behavior` to disable them. Use `idle` as the base for the existing app's rest behavior.

The library validates playback modes, timing, references, motion channels, keyframes, and idle variants at startup. To check changes, run `.venv/bin/python -m pytest -q` and `.venv/bin/python run_pet.py --smoke-test` (use `.venv\Scripts\python` on Windows). The preview scripts listed in the README render with this same configuration.
