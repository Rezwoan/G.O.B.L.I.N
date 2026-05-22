# G.O.B.L.I.N (AutoLoot CoC v3) — Product & Software Requirements
Guided Operation Bot for Looting, Invasion, and Navigation

---

## 1. Product Overview

A Windows desktop bot that automates Clash of Clans on Google Play Games PC via ADB. Given a task (farm X loot, upgrade Y, collect resources), it runs unattended, completes the task, and stops. Notifies via Discord/Telegram. Ships as a standalone EXE with a GUI.

**Not in scope:** multi-account parallel runs, cloud hosting, iOS/Android support, high-skill attacks (Queen Walks, LavaLoon etc.), automatic account switching.

---

## 2. Goals

| # | Goal |
|---|------|
| G1 | Works on any screen resolution — no hardcoded pixel coordinates |
| G2 | Survives CoC UI updates without code changes — vision-based not coordinate-based |
| G3 | Three attack strategies selectable by user |
| G4 | Upgrade anything via the in-game upgrade panel, driven by a user-defined priority list |
| G5 | Task-based operation — give it a job, it finishes, it stops |
| G6 | Notifies user of progress and completion remotely |
| G7 | Distributable as a single EXE — no Python install required on target machine |

---

## 3. User Stories

**Farming**
- As a user I want to set loot thresholds so the bot only attacks bases that meet my minimum gold/elixir/DE requirements
- As a user I want to choose which attack strategy the bot uses
- As a user I want the bot to train troops automatically after each attack so it's always ready
- As a user I want the bot to collect from gold mines and elixir collectors before/after farming

**Upgrading**
- As a user I want to define an ordered upgrade priority list (e.g. walls → king → cannons)
- As a user I want the bot to check if I have enough loot before starting an upgrade
- As a user I want the bot to farm until it has enough loot then start the upgrade automatically
- As a user I want the bot to scroll the upgrade panel and find the target item without me specifying where it is

**Tasks**
- As a user I want to chain tasks: "Farm 5M gold, then upgrade King, then stop"
- As a user I want to run a single task and have the bot stop when complete
- As a user I want to receive a Discord/Telegram message when a task completes or errors

**GUI**
- As a user I want to see a live view of what the bot is doing
- As a user I want to start/stop/pause the bot from the GUI
- As a user I want to edit my task queue and upgrade priority list from the GUI

---

## 4. System Architecture

```
┌─────────────────────────────────────────┐
│                   GUI                   │  CustomTkinter
│  Dashboard | Tasks | Upgrades | Settings│
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│              Task Engine                │  Orchestrates everything
│     Queue → Execute → Notify → Stop     │
└──────┬───────────────────────┬──────────┘
       │                       │
┌──────▼──────┐         ┌──────▼──────────┐
│ State Machine│         │  Notify Layer   │
│ IDLE→...    │         │  Discord/Telegram│
└──────┬───────┘         └─────────────────┘
       │
┌──────▼──────────────────────────────────┐
│                Engines                  │
│  Attack | Upgrade | Collect | Navigate  │
└──────┬──────────────────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│              Vision Layer               │
│   YOLOv8n | Tesseract OCR | OpenCV      │
└──────┬──────────────────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│             ADB Interface               │
│   screencap | input tap | input swipe   │
└──────┬──────────────────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│       Google Play Games PC              │
│       CoC process @ 127.0.0.1:5555      │
└─────────────────────────────────────────┘
```

---

## 5. Module Specifications

### 5.1 ADB Interface (`core/adb.py`)

**Responsibilities:** All communication with the device.

| Function | Behavior |
|----------|----------|
| `connect()` | Connect to 127.0.0.1:5555, raise if failed |
| `screenshot() → np.ndarray` | `adb exec-out screencap -p` piped to PIL → numpy BGR |
| `tap(x, y)` | `adb shell input tap x y` — coordinates always in absolute pixels |
| `swipe(x1,y1,x2,y2,duration_ms)` | `adb shell input swipe` |
| `long_press(x, y, duration_ms)` | swipe same point with duration |
| `get_resolution() → (w, h)` | `adb shell wm size` → parse |
| `is_connected() → bool` | health check, auto-reconnect if dropped |

**Coordinate system:** All internal coordinates stored as floats 0.0–1.0 (relative). Converted to absolute pixels at tap time using `get_resolution()`. This is what makes the bot resolution-independent.

**Timing:** All taps include a small randomized delay (base ± 30% jitter) to avoid bot-detection pattern matching. Base delay configurable in settings.

---

### 5.2 Vision Layer (`core/vision.py`)

#### 5.2.1 YOLO Detector

- Model: YOLOv8n (nano — fast enough for real-time on CPU)
- Input: screenshot numpy array
- Output: list of `Detection(label, confidence, bbox_relative)`
- Confidence threshold: 0.6 default, configurable per class
- Inference runs on every screenshot before any engine decision

**YOLO Classes to Label (training data required):**

| Class | Examples needed | Notes |
|-------|----------------|-------|
| `btn_attack` | 50 | "Attack" button on home village |
| `btn_next` | 50 | Next/Find Match in matchmaking |
| `btn_end_battle` | 40 | End battle button |
| `btn_upgrade` | 60 | Upgrade confirm button |
| `btn_collect` | 40 | Collect from mine/collector |
| `troop_icon` | 80 | Any troop card in army bar |
| `hero_icon` | 60 | King/Queen/Warden/Champion buttons |
| `spell_icon` | 50 | Spell cards in army bar |
| `upgrade_panel` | 60 | The transparent scrollable upgrade overlay |
| `loot_bag` | 40 | Post-battle loot bag |
| `builder_idle` | 40 | Builder available indicator |
| `mine_full` | 40 | Gold mine / elixir collector ready to collect |
| `wall_segment` | 80 | Upgradeable wall in upgrade panel |

Total: ~700 labeled instances across 300–500 screenshots. Collect screenshots across multiple game states, TH levels, and times of day (lighting/background varies).

**Labeling tool:** Roboflow free tier. Export as YOLOv8 format. Train via `ultralytics` Python package locally.

#### 5.2.2 Deployment Zone Detection (OpenCV — no YOLO)

The red line around the enemy base before troop deployment is detected via HSV masking + frame differencing.

```
Step 1 — Capture two frames 200ms apart (before any tap)
Step 2 — Convert both to HSV
Step 3 — Mask red pixels in both:
          Lower red: H(0-10), S(120-255), V(70-255)
          Upper red: H(170-180), S(120-255), V(70-255)
          Combined = lower_mask | upper_mask
Step 4 — Frame diff: abs(frame2_mask - frame1_mask)
          Only pixels that are red AND changed = deployment boundary
Step 5 — findContours on diff result
Step 6 — Filter: keep largest contour with area > 15% of screen area
Step 7 — Store contour points as relative coordinates
```

From the contour, generate deployment points per strategy:
- **Surround:** `np.linspace(0, len(contour)-1, N)` → N evenly spaced points
- **One side:** filter points where x < contour_bbox.x + bbox_width/3
- **One corner:** filter points within radius R of nearest corner of contour bbox

#### 5.2.3 OCR (`core/ocr.py`)

- Engine: Tesseract via `pytesseract`
- Config: `--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789,`
- Preprocessing per region before OCR:
  1. Crop region from screenshot
  2. Scale up 3x (Tesseract accuracy improves with larger input)
  3. Convert to grayscale
  4. Adaptive threshold (not global — handles transparency/varying backgrounds)
  5. Invert if background is dark

**OCR Regions (defined as relative coordinates, calibrated once):**

| Region ID | Content | Weight used |
|-----------|---------|-------------|
| `home_gold` | Gold on home village | Bold |
| `home_elixir` | Elixir on home village | Bold |
| `home_dark` | Dark elixir on home village | Bold |
| `enemy_gold` | Enemy gold during search | Bold |
| `enemy_elixir` | Enemy elixir during search | Bold |
| `enemy_dark` | Enemy dark elixir | Bold |
| `upgrade_cost` | Cost shown in upgrade confirmation | Bold |
| `upgrade_timer` | Time shown in upgrade confirmation | Regular |
| `troop_count` | Count next to troop card | Regular |
| `builder_count` | Available builder count | Bold |

OCR output always parsed as `int` after stripping commas. If parse fails, return `None` and log — never crash.

---

### 5.3 State Machine (`core/state_machine.py`)

States and valid transitions:

```
IDLE ──────────────────────────────► IDLE (no task)
  │
  ▼ (task received)
HOME_VILLAGE ◄──────────────────────────────────────┐
  │                                                  │
  ├──► SEARCHING ──► ATTACKING ──► POST_BATTLE ──────┤
  │                                                  │
  ├──► UPGRADING ────────────────────────────────────┤
  │                                                  │
  ├──► COLLECTING ───────────────────────────────────┤
  │                                                  │
  └──► ERROR_RECOVERY ───────────────────────────────┘
```

**State detection:** Each state has a `detect(screenshot) → bool` method using YOLO. The state machine calls all detectors on each screenshot and sets state to the first match. If no state matches after 3 retries → `ERROR_RECOVERY`.

**ERROR_RECOVERY behavior:**
1. Take screenshot
2. Check for known interruptors: event popup, shield prompt, disconnection dialog, maintenance screen
3. If recognized → dismiss and return to last known state
4. If unrecognized after 3 attempts → stop bot, send error notification with screenshot attached

---

### 5.4 Attack Engine (`engines/attack_engine.py`)

**Flow:**

```
1. Navigate to matchmaking screen
2. Tap "Find a Match"
3. OCR enemy loot values
4. If loot < thresholds → tap Next → goto 2
5. If loot >= thresholds → proceed to deploy
6. Detect red deployment line (HSV method)
7. Generate deployment points from strategy
8. Deploy troops: cycle through points, tap each, one troop per tap
9. Deploy heroes (if available and enabled)
10. Deploy spells (center of base — fixed relative coord)
11. Wait for battle end (YOLO detects end button OR timer OCR reads 0)
12. Tap end → OCR loot gained → log to SQLite
13. Return to HOME_VILLAGE
```

**Army reader:**
- YOLO detects troop icons in army bar
- OCR reads count next to each icon
- Builds dict: `{troop_label: count}`
- Strategy selector matches army dict against user-configured profiles
- If no profile matches → use default strategy set in settings

**Troop deployment:**
- Troops deployed one type at a time in sequence configured by user
- Each tap includes small random offset within detected deployment point (±5px relative)
- Delay between taps: configurable (default 150ms ± 30%)
- Heroes tapped after main army unless configured otherwise
- Spells dropped at relative screen center (0.5, 0.5) — adjustable in settings

---

### 5.5 Upgrade Engine (`engines/upgrade_engine.py`)

**Critical prerequisite:** Before opening upgrade panel, navigate to village corner + max zoom to freeze background behind the transparent panel.

**Flow:**

```
1. Move camera to corner (swipe to edge, zoom in max via pinch gesture)
2. Open upgrade panel (YOLO detects button → tap)
3. Begin scroll-search loop:
   a. Screenshot → CLAHE → adaptive threshold on panel region
   b. YOLO detect items in panel region
   c. OCR read item labels in panel
   d. Check each detected item against priority list
   e. If target found → tap it → upgrade confirmation flow
   f. If not found → check if bottom reached (frame diff of panel between two screenshots)
   g. If not bottom → swipe up inside panel region → goto a
   h. If bottom → target not available (log, move to next priority item)
4. Upgrade confirmation:
   a. YOLO detect upgrade button
   b. OCR read cost
   c. Compare cost to current loot (OCR home loot)
   d. If sufficient → tap upgrade → confirm → log → notify
   e. If insufficient → close panel → queue farming task for required amount
5. Track seen items in session set to avoid re-processing on next scroll pass
```

**Bottom detection:** Take screenshot at position A, scroll, take screenshot at position B. If pixel diff of panel region < threshold → bottom reached.

**Wall upgrades specifically:** Wall items in the panel are labeled "Wall" with a level indicator. Bot upgrades them in order of appearance (top to bottom as they appear in the panel). Each wall segment is a separate tappable item in the list.

---

### 5.6 Task Engine (`engines/task_engine.py`)

**Task types:**

| Task | Parameters | Done when |
|------|-----------|-----------|
| `FarmTask` | `n_attacks: int` OR `until_gold: int, until_elixir: int, until_dark: int` | Attack count reached OR loot threshold reached |
| `UpgradeTask` | `target: str` (matches upgrade panel label) | Upgrade confirmed |
| `CollectTask` | none | All available collectors tapped |
| `SequenceTask` | `tasks: List[Task]` | All sub-tasks complete |

**Queue behavior:**
- Tasks execute in order
- On task failure: retry up to `max_retries` (default 3), then skip and notify
- On queue complete: bot stops, sends completion notification
- Queue persisted to `tasks.toml` so it survives restarts

**Condition chains example:**
```toml
[[tasks]]
type = "FarmTask"
until_gold = 5000000
until_elixir = 5000000

[[tasks]]
type = "UpgradeTask"
target = "Barbarian King"
```
Bot farms until 5M gold + elixir accumulated, then upgrades King, then stops.

---

### 5.7 Notification Layer (`notify/`)

**Discord (`notify/discord.py`):**
- Webhook URL stored in config
- Sends rich embed with: event type, timestamp, relevant values (loot collected, upgrade started, error message)
- On error events: attaches screenshot as file upload

**Telegram (`notify/telegram.py`):**
- Bot token + chat ID stored in config
- Same events as Discord
- Optional: receive `/status`, `/stop` commands via polling

**Events that trigger notifications:**

| Event | Discord | Telegram |
|-------|---------|----------|
| Task started | ✓ | ✓ |
| Task completed | ✓ | ✓ |
| Upgrade started | ✓ | ✓ |
| Insufficient loot for upgrade | ✓ | ✓ |
| Error / unknown state | ✓ + screenshot | ✓ + screenshot |
| Bot stopped | ✓ | ✓ |

---

### 5.8 GUI (`gui/`)

Framework: CustomTkinter. Dark theme. Tabs:

**Dashboard tab:**
- Live screenshot feed (refreshes every 2s)
- Current state label
- Session stats: attacks done, loot collected this session, time running
- Start / Pause / Stop buttons

**Tasks tab:**
- Add task (type selector + parameters)
- Ordered task list with drag-to-reorder
- Remove task button
- Save/load queue

**Upgrades tab:**
- Ordered upgrade priority list
- Add item (text input matching upgrade panel labels)
- Drag to reorder
- Save list

**Army tab:**
- List of army profiles
- Each profile: name + troop composition + assigned attack strategy
- Add/edit/delete profiles

**Settings tab:**
- ADB port (default 5555)
- Loot thresholds (gold, elixir, dark elixir minimums)
- Attack delay base (ms)
- Notification config (Discord webhook URL, Telegram token + chat ID)
- Toggle: collect resources before farming
- Toggle: heroes enabled in attacks
- Toggle: spells enabled in attacks

**Log tab:**
- Scrollable log with timestamps
- Color coded: INFO (white), SUCCESS (green), WARNING (yellow), ERROR (red)

---

## 6. Data Storage

### SQLite schema (`data/autoloot.db`)

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT,
    ended_at TEXT,
    attacks_done INTEGER,
    gold_collected INTEGER,
    elixir_collected INTEGER,
    dark_collected INTEGER
);

CREATE TABLE attacks (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    timestamp TEXT,
    strategy TEXT,
    enemy_gold INTEGER,
    enemy_elixir INTEGER,
    enemy_dark INTEGER,
    loot_gold INTEGER,
    loot_elixir INTEGER,
    loot_dark INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE upgrades (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    timestamp TEXT,
    target TEXT,
    cost_gold INTEGER,
    cost_elixir INTEGER,
    cost_dark INTEGER,
    success INTEGER
);

CREATE TABLE logs (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    timestamp TEXT,
    level TEXT,
    message TEXT
);
```

### Config files (TOML)

`config.toml` — all user settings  
`priorities.toml` — upgrade priority list  
`tasks.toml` — saved task queue  
`armies.toml` — army profiles + strategy mappings  

---

## 7. Repo Structure

```
autoloot-coc/
├── core/
│   ├── adb.py
│   ├── vision.py
│   ├── ocr.py
│   ├── state_machine.py
│   └── navigator.py
├── engines/
│   ├── attack_engine.py
│   ├── upgrade_engine.py
│   ├── task_engine.py
│   └── collect_engine.py
├── strategies/
│   ├── base_strategy.py
│   ├── surround.py
│   ├── one_side.py
│   └── one_corner.py
├── notify/
│   ├── discord.py
│   └── telegram.py
├── gui/
│   ├── app.py
│   ├── dashboard.py
│   ├── tasks.py
│   ├── upgrades.py
│   ├── army.py
│   ├── settings.py
│   └── log_view.py
├── models/
│   └── coc_yolo.pt
├── tools/
│   └── capture_tool.py       ← screenshot collector for training data
├── data/
│   └── autoloot.db
├── config.toml
├── priorities.toml
├── tasks.toml
├── armies.toml
├── main.py
├── requirements.txt
└── autoloot.spec              ← PyInstaller spec
```

---

## 8. Development Phases

### Phase 1 — ADB Foundation
**Goal:** Can connect, screenshot, and tap reliably.

- [ ] Install ADB platform tools, verify connection to Google Play Games PC
- [ ] `adb.py`: connect, screenshot pipeline, tap, swipe, get_resolution
- [ ] Relative coordinate system utilities
- [ ] CLI test script: connect → screenshot → tap a known button → verify

**Done when:** Can take a screenshot every 500ms and inject a tap that registers in the game.

---

### Phase 2 — YOLO Training
**Goal:** Model that detects CoC UI elements reliably.

- [ ] Build `tools/capture_tool.py` — hotkey (F9) saves timestamped screenshot to `/training_data/raw/`
- [ ] Collect 300–500 screenshots across: home village, matchmaking, battle, upgrade panel, post-battle
- [ ] Upload to Roboflow, label all classes from section 5.2.1
- [ ] Train YOLOv8n via `ultralytics` locally: `yolo train data=dataset.yaml model=yolov8n.pt epochs=100`
- [ ] Validate: run inference on 20 held-out screenshots, check all classes detect correctly
- [ ] Save weights to `models/coc_yolo.pt`

**Done when:** All classes detect at >90% precision on validation set.

---

### Phase 3 — OCR Integration
**Goal:** Can read all numeric values from the game.

- [ ] Install Tesseract, configure PATH
- [ ] `ocr.py`: preprocessing pipeline + `read_region(screenshot, region_id) → int | None`
- [ ] Calibrate all OCR regions from section 5.2.3 by measuring on actual screenshots
- [ ] Test: OCR all regions against known values, log accuracy
- [ ] Tune preprocessing (scale factor, threshold params) until >95% accuracy on digits

**Done when:** Gold, elixir, dark elixir, upgrade cost all read correctly >95% of the time.

---

### Phase 4 — State Machine + Navigation
**Goal:** Bot knows where it is and can get to any screen.

- [ ] `state_machine.py`: detect() per state using YOLO
- [ ] `navigator.py`: transition functions between all states
- [ ] Handle interruptors: event popups, shield prompts, disconnection dialogs
- [ ] `ERROR_RECOVERY`: dismiss known popups, send notification + screenshot if unknown
- [ ] Test: manually put game in each state, verify detection is correct

**Done when:** Bot can navigate from home village → matchmaking → home village → upgrade panel → home village reliably 10 times in a row.

---

### Phase 5 — Attack Engine
**Goal:** Full attack cycle working end to end.

- [ ] Red line detection: HSV mask + frame diff + contour extraction
- [ ] Three strategy sampling functions (surround, one_side, one_corner)
- [ ] Base search loop: find match → OCR loot → compare threshold → next or attack
- [ ] Army reader: YOLO troop icons + OCR counts
- [ ] Troop deployment loop with randomized tap offsets
- [ ] Hero + spell deployment
- [ ] Battle end detection + loot OCR + SQLite log
- [ ] Test: 10 consecutive attack cycles without manual intervention

**Done when:** 10 attacks complete unattended with correct loot logged.

---

### Phase 6 — Upgrade Engine
**Goal:** Can find any item in the upgrade panel and upgrade it.

- [ ] Camera corner + max zoom navigation before opening panel
- [ ] Panel region CLAHE + adaptive threshold preprocessing
- [ ] Scroll-search loop with bottom detection
- [ ] Upgrade confirmation flow: cost check → tap → confirm
- [ ] Insufficient loot handling
- [ ] Session seen-items tracking
- [ ] Test: upgrade 5 different items from priority list unattended

**Done when:** Bot finds and upgrades any item in the priority list, handles scroll correctly, stops when all items unavailable.

---

### Phase 7 — Task Engine
**Goal:** Full task queue working end to end.

- [ ] `task_engine.py`: all task types, queue, execute, retry, stop
- [ ] Condition chain: FarmTask(until_gold=X) → UpgradeTask → stop
- [ ] Queue persistence to `tasks.toml`
- [ ] Test: run a full sequence — farm → upgrade → collect → stop

**Done when:** Full condition chain runs unattended and bot stops on completion.

---

### Phase 8 — Notifications
**Goal:** Discord and Telegram events working.

- [ ] `discord.py`: webhook sender with embeds + screenshot attach
- [ ] `telegram.py`: bot sender + `/status` `/stop` command polling
- [ ] Wire all events from section 5.7
- [ ] Test: trigger each event, verify message received

**Done when:** All events fire on Discord and Telegram with correct content.

---

### Phase 9 — GUI
**Goal:** Usable desktop interface.

- [ ] CustomTkinter app skeleton with tab navigation
- [ ] Dashboard: live feed thread (non-blocking), state label, stats
- [ ] Tasks tab: add/remove/reorder task queue, save/load
- [ ] Upgrades tab: priority list editor
- [ ] Army tab: profile editor
- [ ] Settings tab: all config values
- [ ] Log tab: scrollable color-coded log
- [ ] Wire start/pause/stop to task engine
- [ ] Test: run full session from GUI start to completion notification

**Done when:** Full session can be configured and run entirely from GUI.

---

### Phase 10 — EXE Packaging
**Goal:** Single distributable EXE.

- [ ] `autoloot.spec`: bundle YOLO model, Tesseract binary, assets, config defaults
- [ ] First-run setup: ADB path config, connection test, create default config files
- [ ] Test on clean Windows machine (no Python installed)
- [ ] Verify EXE starts, connects, and runs a task end-to-end

**Done when:** EXE runs on a fresh Windows machine with no prerequisites.

---

## 9. Dependencies (`requirements.txt`)

```
ultralytics>=8.0.0
opencv-python>=4.8.0
pytesseract>=0.3.10
Pillow>=10.0.0
customtkinter>=5.2.0
python-telegram-bot>=20.0
requests>=2.31.0
toml>=0.10.2
numpy>=1.24.0
```

External (not pip):
- ADB platform tools — added to PATH
- Tesseract binary — added to PATH, configured in `pytesseract.pytesseract.tesseract_cmd`

---

## 10. Known Risks

| Risk | Mitigation |
|------|-----------|
| CoC UI update breaks YOLO classes | Retrain affected classes only — takes hours not days with existing labeled data as base |
| Tesseract misreads loot values | Add sanity bounds check (loot can't be >10M gold etc.), log misreads for preprocessing tuning |
| Red line detection fails on certain base layouts | Fallback: fixed border ring deployment points at 8% inset from screen edges |
| Upgrade panel OCR fails due to background bleed | Corner + zoom fix handles most cases; CLAHE + adaptive threshold handles the rest |
| ADB connection drops mid-session | Auto-reconnect in `adb.py`, state machine handles recovery |
| Supercell ban detection | Randomized delays, jitter on all tap coordinates, avoid 24/7 continuous operation |
EOF