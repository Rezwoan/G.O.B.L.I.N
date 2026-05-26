# G.O.B.L.I.N Toolkit

**Game Operation Bot: Loot, Interact & Navigate**

A Windows desktop overlay for automating Clash of Clans running through **Google Play Games on PC**.  
No emulator, no ADB — pure screen capture + native Win32 input injection.

---

## Features

| | |
|---|---|
| 🎯 **Visual detection** | OpenCV template matching — capture any button once, detect it forever |
| 🖱 **Precise clicking** | Foreground (real cursor) or background (PostMessage) click modes |
| ⚔ **Full attack cycle** | 15-point flow: detect home → zoom → match → attack → deploy → return |
| 🪖 **Army deployment** | Troops, siege machine, heroes, and ability activation in order |
| 🚨 **Alarm system** | Beep + mouse-move detection pauses the bot when something goes wrong |
| 👁 **Stealth overlay** | Hidden from game screenshots via `WDA_EXCLUDEFROMCAPTURE` |
| ⌨ **Global hotkey** | F9 (configurable) shows / hides the overlay without alt-tabbing |
| 🎨 **Dark UI** | Solid, resizable tkinter window — no transparency issues |

---

## Demo

The overlay floats on top of Clash of Clans and stays hidden from the game's own screenshot system.

**Configure tab** — add buttons via live Capture or fixed coordinates:

![Configure tab](demo/Screenshot%202026-05-26%20202541.png)

**Bot Flow: Attack** — the full automated attack cycle:

![Attack flow](demo/Screenshot%202026-05-26%20202551.png)

**Bot Flow: Upgrade** — automated resource-spending loop:

![Upgrade flow](demo/Screenshot%202026-05-26%20202615.png)

---

## How It Works

```
toolkit.py
│
├── core/config.py     — All persistent state (settings, buttons, army, flow)
├── core/screen.py     — mss screenshots + win32 click/hold/scroll
├── core/vision.py     — OpenCV template matching + deploy-zone detection
├── core/alarm.py      — Beep alarm with mouse-move silence detection
│
└── ui/
    ├── app.py         — tk.Tk root, tabs, hotkey, log, settings panel
    ├── configure_tab.py — Button capture, troop/hero/deploy setup
    ├── flow_tab.py    — Step list editor + bot execution engine
    └── theme.py       — Dark colour palette + ttk style definitions
```

The bot reads the configured **flow.json** step list and executes each step in a background thread.  
The UI stays responsive at all times; all state updates are dispatched back to the main thread via `root.after(0, fn)`.

---

## Requirements

- **Windows 10 / 11**
- **Python 3.10+** (3.11 recommended)
- **Google Play Games on PC** with Clash of Clans installed and running in a window

```
pip install -r requirements.txt
```

```
mss
opencv-python
pywin32
pynput
pillow
```

> `tkinter` is included with Python on Windows — no extra install needed.

---

## Installation

```bash
git clone https://github.com/yourname/goblin.git
cd goblin
pip install -r requirements.txt
python toolkit.py
```

---

## Usage

### 1 — Pick the game window

Click **Pick Window**, select **Clash of Clans**, click **Confirm**.  
The toolbar shows the detected window size and position.

### 2 — Configure buttons

Go to the **Configure** tab. For each screen context (Home, Attack, Post-Attack, Upgrade):

| Method | When to use |
|--------|-------------|
| **Capture** | Drag a box around the button in a live screenshot — saves a template image |
| **Set Coord** | Click anywhere on screen to save a fixed pixel position |
| **Test** | Runs detection and previews the match result in an OpenCV window |

Set up at minimum: `home.attack`, `attack.find_match`, `attack.attack_now`, `attack.next_base`, `post_attack.return_home`.

### 3 — Set up troops

In **Troops & Deploy**:

1. **Add Troop** — capture or coord each troop button, set count and deploy-at positions
2. **Siege Machine** — same as troops
3. **Heroes** — add up to 4, capture each hero button
4. **Deploy Positions** — click **Auto-detect** to scan the red border, or **＋ Manual** to click positions one by one

### 4 — Review the bot flow

Open **Bot Flow → Attack**. The default 12-step plan covers the full 15-point cycle:

| # | Step | Action |
|---|------|--------|
| 1 | Confirm at home | DETECT `home.attack` |
| 2 | Zoom out | ZOOM_OUT ×5 |
| 3 | Click attack | CLICK `home.attack` |
| 4 | Wait for matchmaking | DETECT `attack.find_match` |
| 5 | Start search | CLICK `attack.find_match` |
| 6 | Wait for base | DETECT `attack.attack_now` |
| 7 | Commit to attack | CLICK `attack.attack_now` |
| 8 | Wait for deploy screen | DETECT `attack.next_base` |
| 9 | Deploy full army | DEPLOY (troops → siege → heroes → abilities) |
| 10 | Wait for battle end | DETECT `post_attack.return_home` (10 min timeout) |
| 11 | Return home | CLICK `post_attack.return_home` |
| 12 | Confirm home | DETECT `home.attack` |

Steps can be reordered, added, deleted, or have their parameters tuned directly in the UI.  
Click **↺ Reset Flows** to restore the default plan at any time.

### 5 — Run

Click **▶ Run**. The overlay hides itself so clicks land on the game.  
- **⏸ Pause** — suspends after the current step; overlay reappears
- **■ Stop** — cancels the loop cleanly
- **Alarm** — fires when a DETECT step times out; move the mouse to silence it, then click Resume

---

## Bot Flow step types

| Action | What it does | Key params |
|--------|-------------|------------|
| `DETECT` | Waits until a button appears on screen | `detect_timeout_ms`, `on_fail` |
| `CLICK` | Clicks a configured button (image or coord) | `repeat` |
| `HOLD` | Long-press a button | `hold_ms` |
| `ZOOM_OUT` | Scrolls out at the game window centre | `repeat` (ticks) |
| `DEPLOY` | Full army sequence in one step | configured in Troops & Deploy |
| `SCROLL_SEARCH` | Scrolls until a button appears | `scroll_direction`, `max_scrolls`, `on_fail` |

`on_fail` options: `ALARM_WAIT` (default) · `SKIP` · `STOP`

---

## Settings

Open the **▶ Settings** drawer at the bottom of the window:

| Setting | Default | Description |
|---------|---------|-------------|
| Click delay | 150 ms | Pause injected between repeated clicks |
| Match threshold | 0.80 | OpenCV confidence required for a template match (0–1) |
| Click mode | foreground | `foreground` moves the real cursor; `background` uses PostMessage |
| Toggle hotkey | `<f9>` | Global hotkey to show/hide the overlay |

---

## Data files

All state is saved automatically — no manual editing required.

| File | Contents |
|------|----------|
| `config.json` | App settings (hotkey, threshold, window title…) |
| `buttons.json` | Button slots organised by screen context |
| `army.json` | Troop / hero / siege / deploy-position config |
| `flow.json` | Bot plan: step lists + attacks-per-upgrade |
| `templates/` | PNG template images captured in the Configure tab |

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| F9 (default) | Toggle overlay visibility |
| Esc | Cancel an active Capture or Set Coord operation |
| Mouse move | Silence an active alarm and trigger a pause |

---

## Tech stack

| Library | Purpose |
|---------|---------|
| `tkinter` + `ttk` | UI (ships with Python — no install) |
| `mss` | Fast multi-monitor screen capture |
| `opencv-python` | Template matching, deploy-zone detection |
| `pywin32` | Win32 API — window lookup, click injection, focus |
| `pynput` | Global hotkeys, mouse listeners |
| `Pillow` | Image capture overlay, template I/O |

---

## License

MIT — do whatever you want, just don't get banned.
