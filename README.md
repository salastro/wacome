# wacome

A visual front-end for `xsetwacom` (X11 only).

- **Screen & Area**: shows all monitors to scale. Map the tablet to one monitor or all of them by clicking, or drag to map it to a custom region. You can keep proportions so there is no stretching, and see the tablet surface with a draggable active area and rotation. Dotted lines connect each tablet corner to the screen corner it maps to. A dot tracks the pointer or pen live, and *Show on screen* / *Identify monitors* highlight the real screens.
- **Pressure**: drag-to-edit Bezier curve with presets, a click-threshold slider, and a test pad whose strokes follow pressure. A red marker on the curve shows how hard you are pressing right now.
- **Buttons**: a drawing of the pen with clickable tip, side buttons and eraser. Assign mouse buttons, keyboard shortcuts, pan/scroll, or a raw action. Pressing a physical button over the test pad lights up the matching part. Pad buttons appear when the tablet has them.
- **Advanced**: absolute/relative mode, jitter suppression, smoothing, and touch/gesture toggles.

Changes stay *pending* (dashed orange) until you click **Apply** (Ctrl+Enter), or tick **Live** to apply as you edit. The *Commands* panel logs every `xsetwacom` call and can copy them as a shell script.

## Profiles & persistence

Profiles are JSON files in `~/.config/wacome/profiles/`. Mark one as **Default** and tick **Apply on login**. This installs `~/.config/autostart/wacome.desktop`, which runs `wacome --daemon`: it applies the default profile at login and applies it again whenever the tablet is re-plugged or the monitor layout changes. The GUI does the same while it is open.

If a profile targets a monitor that is not connected, it falls back to the primary monitor.

## Usage

```sh
python -m wacome            # GUI
python -m wacome --list     # tablets, monitors, profiles
python -m wacome --apply [PROFILE] [--dry-run] [-v]
python -m wacome --daemon [PROFILE]
pip install --user .        # installs the `wacome` command
```

Requires Python ≥ 3.10, PySide6, `xsetwacom` (xf86-input-wacom), `xrandr`, and `xinput`.

## Tests

```sh
python -m pytest
```
