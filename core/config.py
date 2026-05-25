"""
Persistent configuration manager.

Handles loading/saving all JSON data files:
  config.json  — general settings (click delay, threshold, opacity, hotkey)
  buttons.json — button slots organised by screen context
  army.json    — troop/hero/siege configs + deploy positions
  flow.json    — bot plan: attacks_per_upgrade, attack_steps, upgrade_steps

Migration
---------
Old buttons.json used a flat format: {"btn_attack_home": {...}, ...}
This is automatically detected and migrated to the new context-organised
format on first load.  The migrated file is immediately written back to disk
so the migration never runs again.

Old flow.json was a plain list of steps; it is migrated to the new dict
format with attack_steps / upgrade_steps keys on first load.
"""

import json
from pathlib import Path
from typing import Any


class AppConfig:
    """
    Central data store.  Every piece of persistent state lives here.
    UI and core modules read/mutate this, then call the matching save_*().
    """

    # ── Global settings defaults ──────────────────────────────────────────

    DEFAULTS: dict[str, Any] = {
        "click_delay_ms":   150,
        "match_threshold":  0.80,
        "toggle_hotkey":    "<f9>",
        "window_title":     "",
        "opacity":          0.92,
        "click_mode":       "foreground",   # "foreground" or "background"
    }

    # ── Button slot seeds (new context-organised format) ──────────────────
    # Every slot here appears in the Configure tab automatically.
    # Users set an image template or a fixed coordinate for each one.

    SEED_BUTTONS: dict[str, dict[str, dict]] = {
        "home": {
            # Detected at the start of every attack cycle (confirms home screen)
            "attack": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
            # Opens the "Upgradables" panel (hammer / builder icon)
            "upgradables_icon": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
        },
        "attack": {
            "find_match": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
            # Detected when a base is ready — triggers troop deployment
            "next_base": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
            "attack_now": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
            "surrender": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
        },
        "post_attack": {
            # Detected when the battle ends — then clicked to go home
            "return_home": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
            # Optional OK / close popup that sometimes appears after returning home
            "ok_popup": {
                "mode": "COORD", "coord": None,
                "template": None, "configured": False,
            },
        },
        # Slots used in the upgrade cycle
        "upgrade": {
            # The walls entry inside the upgradables list (used for SCROLL_SEARCH)
            "walls_item": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
            # "Upgrade with Gold" button in the wall upgrade window
            "gold_btn": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
            # "Upgrade with Elixer" button in the wall upgrade window
            "elixer_btn": {
                "mode": "IMAGE", "coord": None,
                "template": None, "configured": False,
            },
        },
    }

    # ── Migration map: old flat key → (context, name) ────────────────────
    # Maps every known v1 key to its new location in the context dict.

    _BUTTON_MIGRATION: dict[str, tuple[str, str]] = {
        "btn_attack_home":  ("home",        "attack"),
        "btn_find_match":   ("attack",      "find_match"),
        "btn_next_base":    ("attack",      "next_base"),
        "btn_attack_now":   ("attack",      "attack_now"),
        "btn_surrender":    ("attack",      "surrender"),
        "btn_return_home":  ("post_attack", "return_home"),
        "btn_ok_popup":     ("post_attack", "ok_popup"),
        "btn_reload":       ("home",        "reload"),
    }

    # ── Army defaults ─────────────────────────────────────────────────────

    DEFAULT_ARMY: dict[str, Any] = {
        "troops":             [],
        "siege": {
            "name": "", "mode": "IMAGE",
            "coord": None, "template": None,
            "configured": False, "deploy_at": "all",
        },
        "heroes":             [],
        "deploy_positions":   [],
        "deploy_tap_delay_ms": 200,
        "ability_delay_ms":   2500,   # wait after troop deploy before activating abilities
    }

    # ── Default flow steps ────────────────────────────────────────────────
    # These are written to flow.json the first time the app runs (when both
    # step lists are empty).  Users then just fill in images / coords for
    # the referenced slots in the Configure tab.  They can delete, reorder,
    # or add steps at any time.  "Reset to Defaults" in the Bot Flow tab
    # restores these lists.

    DEFAULT_ATTACK_STEPS: list[dict] = [
        # ── Step 1 ─ Confirm we are on the home screen ────────────────────
        # Detect the Attack button on the home screen.
        # If we can see it we know we are home and safe to start the cycle.
        {
            "id": "atk_01", "action": "DETECT",
            "target": "home.attack",
            "detect_timeout_ms": 60_000,
            "on_fail": "ALARM_WAIT",
            "delay_ms": 300,
        },
        # ── Step 2 ─ Zoom out ─────────────────────────────────────────────
        # Scroll the camera back to full zoom so the base is fully visible
        # and click targets are in their expected screen positions.
        {
            "id": "atk_02", "action": "ZOOM_OUT",
            "repeat": 5,
            "delay_ms": 500,
        },
        # ── Step 3 ─ Click the Attack button ─────────────────────────────
        # Opens the attack lobby / matchmaking screen.
        {
            "id": "atk_03", "action": "CLICK",
            "target": "home.attack",
            "repeat": 1,
            "delay_ms": 1500,
        },
        # ── Step 4 ─ Detect "Find a Match" ────────────────────────────────
        # Wait for the matchmaking button to appear before we click it.
        {
            "id": "atk_04", "action": "DETECT",
            "target": "attack.find_match",
            "detect_timeout_ms": 30_000,
            "on_fail": "ALARM_WAIT",
            "delay_ms": 300,
        },
        # ── Step 5 ─ Click "Find a Match" ────────────────────────────────
        # Starts the matchmaking search.
        {
            "id": "atk_05", "action": "CLICK",
            "target": "attack.find_match",
            "repeat": 1,
            "delay_ms": 2000,
        },
        # ── Step 6 ─ Detect the Attack button on the opponent's base ──────
        # This button appears once a base is loaded and we can attack.
        {
            "id": "atk_06", "action": "DETECT",
            "target": "attack.attack_now",
            "detect_timeout_ms": 30_000,
            "on_fail": "ALARM_WAIT",
            "delay_ms": 300,
        },
        # ── Step 7 ─ Click the Attack button ─────────────────────────────
        # Commits to attacking the found base.
        {
            "id": "atk_07", "action": "CLICK",
            "target": "attack.attack_now",
            "repeat": 1,
            "delay_ms": 500,
        },
        # ── Step 8 ─ Detect the Next button ──────────────────────────────
        # The Next button appears when the battle field is loaded and we
        # can begin deploying troops.  Detecting it = attack can begin.
        {
            "id": "atk_08", "action": "DETECT",
            "target": "attack.next_base",
            "detect_timeout_ms": 180_000,
            "on_fail": "ALARM_WAIT",
            "delay_ms": 300,
        },
        # ── Steps 9-12 ─ Deploy full army ────────────────────────────────
        # Deploys in this fixed order:
        #   9.  Select & deploy troops (at configured deploy positions)
        #  10.  Deploy siege machine
        #  11.  Deploy heroes
        #  12.  Activate hero abilities (after ability_delay_ms)
        {
            "id": "atk_09", "action": "DEPLOY",
            "delay_ms": 500,
        },
        # ── Step 13 ─ Detect "Return Home" ────────────────────────────────
        # This button appears when the battle ends.  We wait up to 10 minutes.
        {
            "id": "atk_10", "action": "DETECT",
            "target": "post_attack.return_home",
            "detect_timeout_ms": 600_000,
            "on_fail": "ALARM_WAIT",
            "delay_ms": 300,
        },
        # ── Step 14 ─ Click "Return Home" ────────────────────────────────
        # Returns us to the village.  Long delay to let the screen transition.
        {
            "id": "atk_11", "action": "CLICK",
            "target": "post_attack.return_home",
            "repeat": 1,
            "delay_ms": 4000,
        },
        # ── Step 15 ─ Confirm back at home ────────────────────────────────
        # Re-detect the home Attack button.  Success = one full cycle done.
        # Failure = something went wrong during the return, alarm fires.
        {
            "id": "atk_12", "action": "DETECT",
            "target": "home.attack",
            "detect_timeout_ms": 60_000,
            "on_fail": "ALARM_WAIT",
            "delay_ms": 500,
        },
    ]

    DEFAULT_UPGRADE_STEPS: list[dict] = [
        # 1. Open the "Upgradables" panel (hammer / builder icon on home screen)
        {
            "id": "upg_01", "action": "CLICK",
            "target": "home.upgradables_icon",
            "repeat": 1,
            "delay_ms": 1500,
        },
        # 2. Scroll down the list until the "Walls" item is visible
        {
            "id": "upg_02", "action": "SCROLL_SEARCH",
            "target": "upgrade.walls_item",
            "scroll_direction": "DOWN",
            "max_scrolls": 20,
            "on_fail": "ALARM_WAIT",
            "delay_ms": 500,
        },
        # 3. Click the Walls item to open the upgrade window
        {
            "id": "upg_03", "action": "CLICK",
            "target": "upgrade.walls_item",
            "repeat": 1,
            "delay_ms": 1000,
        },
        # 4. Upgrade 3 walls with Gold
        {
            "id": "upg_04", "action": "CLICK",
            "target": "upgrade.gold_btn",
            "repeat": 3,
            "delay_ms": 800,
        },
        # 5. Upgrade 3 walls with Elixer
        {
            "id": "upg_05", "action": "CLICK",
            "target": "upgrade.elixer_btn",
            "repeat": 3,
            "delay_ms": 800,
        },
    ]

    # ── Flow (bot plan) defaults ──────────────────────────────────────────

    DEFAULT_FLOW: dict[str, Any] = {
        "attacks_per_upgrade": 40,
        "attack_steps":        [],   # populated from DEFAULT_ATTACK_STEPS on first run
        "upgrade_steps":       [],   # populated from DEFAULT_UPGRADE_STEPS on first run
    }

    # ── Init ──────────────────────────────────────────────────────────────

    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir)
        self.templates_dir = self.root / "templates"
        self.templates_dir.mkdir(exist_ok=True)

        self._paths: dict[str, Path] = {
            "config":  self.root / "config.json",
            "buttons": self.root / "buttons.json",
            "army":    self.root / "army.json",
            "flow":    self.root / "flow.json",
        }

        # Live data — loaded from disk, mutated in-memory, saved on change
        self.settings:  dict[str, Any] = {}
        self.buttons:   dict[str, Any] = {}   # {context: {name: slot_dict}}
        self.army:      dict[str, Any] = {}
        self.flow_data: dict[str, Any] = {}   # attacks_per_upgrade + step lists

        self.load()

    # ── Load / Save ───────────────────────────────────────────────────────

    def load(self):
        """
        Load all data files, apply migrations, and back-fill missing defaults.
        Writes the (possibly migrated) data back to disk immediately.
        """
        # Settings
        self.settings = self._read("config", {})
        for k, v in self.DEFAULTS.items():
            self.settings.setdefault(k, v)

        # Buttons — migrate from old flat format if needed, then seed defaults
        raw_buttons = self._read("buttons", {})
        raw_buttons = self._migrate_buttons(raw_buttons)
        self.buttons = raw_buttons
        for ctx, seeds in self.SEED_BUTTONS.items():
            self.buttons.setdefault(ctx, {})
            for name, slot in seeds.items():
                self.buttons[ctx].setdefault(name, dict(slot))

        # Army
        self.army = self._read("army", {})
        for k, v in self.DEFAULT_ARMY.items():
            if isinstance(v, dict):
                self.army.setdefault(k, dict(v))
            elif isinstance(v, list):
                self.army.setdefault(k, list(v))
            else:
                self.army.setdefault(k, v)
        # Ensure deploy_at / ability fields exist on every entry
        for t in self.army.get("troops", []):
            t.setdefault("deploy_at", "all")
        for h in self.army.get("heroes", []):
            h.setdefault("deploy_at", "all")
        self.army.get("siege", {}).setdefault("deploy_at", "all")
        self.army.setdefault("ability_delay_ms", 2500)

        # Flow — migrate from old list/dict format if needed, then seed defaults
        raw_flow = self._read("flow", {})
        raw_flow = self._migrate_flow(raw_flow)
        self.flow_data = dict(self.DEFAULT_FLOW)
        self.flow_data.update(raw_flow)
        # Ensure both step lists exist
        self.flow_data.setdefault("attack_steps",  [])
        self.flow_data.setdefault("upgrade_steps", [])

        # First-run: populate default step lists when both are empty.
        # A "defaults_applied" flag prevents re-populating after the user
        # deliberately deletes all steps.
        if (not self.flow_data.get("defaults_applied")
                and not self.flow_data["attack_steps"]
                and not self.flow_data["upgrade_steps"]):
            import copy
            self.flow_data["attack_steps"]  = copy.deepcopy(self.DEFAULT_ATTACK_STEPS)
            self.flow_data["upgrade_steps"] = copy.deepcopy(self.DEFAULT_UPGRADE_STEPS)
            self.flow_data["defaults_applied"] = True

        # Persist (writes migrated + defaulted data)
        self.save()

    def save(self):
        """Write all four data files to disk."""
        self.save_settings()
        self.save_buttons()
        self.save_army()
        self.save_flow()

    def save_settings(self): self._write("config",  self.settings)
    def save_buttons(self):  self._write("buttons", self.buttons)
    def save_army(self):     self._write("army",    self.army)
    def save_flow(self):     self._write("flow",    self.flow_data)

    # ── Flow helpers ──────────────────────────────────────────────────────

    def reset_flow_to_defaults(self):
        """
        Overwrite both step lists with the built-in defaults.
        Called when the user clicks "Reset to Default Flow" in the UI.
        """
        import copy
        self.flow_data["attack_steps"]  = copy.deepcopy(self.DEFAULT_ATTACK_STEPS)
        self.flow_data["upgrade_steps"] = copy.deepcopy(self.DEFAULT_UPGRADE_STEPS)
        self.flow_data["defaults_applied"] = True
        self.save_flow()

    # ── Migrations ────────────────────────────────────────────────────────

    def _migrate_buttons(self, raw: dict) -> dict:
        """
        Detect and convert old flat buttons.json format to the new
        context-organised format.

        Old format (v1):  {"btn_attack_home": {...}, "btn_find_match": {...}}
        New format (v2):  {"home": {"attack": {...}}, "attack": {"find_match": {...}}}

        Detection: if any top-level key matches the migration map, treat the
        whole file as old-format and convert every key we know about.
        Unknown old keys are silently dropped.  Already-new-format data
        is returned unchanged.
        """
        if not any(k in self._BUTTON_MIGRATION for k in raw):
            return raw  # already new format (or empty)

        migrated: dict = {}
        for old_key, slot_data in raw.items():
            if old_key in self._BUTTON_MIGRATION:
                ctx, name = self._BUTTON_MIGRATION[old_key]
                migrated.setdefault(ctx, {})[name] = slot_data
            # Unknown old keys are intentionally discarded
        return migrated

    def _migrate_flow(self, raw: Any) -> dict:
        """
        Detect and convert old flow.json formats to the new dict format.

        Old format A (v1): plain list  [step, step, ...]
        Old format B (v2): {"steps": [step, step, ...]}
        New format  (v3):  {"attacks_per_upgrade": N, "attack_steps": [...], ...}
        """
        if isinstance(raw, list):
            # v1: bare list → move to attack_steps
            return {
                "attacks_per_upgrade": 40,
                "attack_steps":        raw,
                "upgrade_steps":       [],
            }
        if isinstance(raw, dict) and "steps" in raw and "attack_steps" not in raw:
            # v2: single "steps" wrapper
            return {
                "attacks_per_upgrade": raw.get("attacks_per_upgrade", 40),
                "attack_steps":        raw["steps"],
                "upgrade_steps":       [],
            }
        return raw  # v3 or empty — already correct

    # ── Slot resolution ───────────────────────────────────────────────────

    def all_slot_keys(self) -> list[str]:
        """
        Return every known slot key in "context.name" format.
        Used to populate target dropdowns in the Bot Flow tab.
        """
        keys: list[str] = []
        for ctx, slots in self.buttons.items():
            for name in slots:
                keys.append(f"{ctx}.{name}")
        for i in range(len(self.army.get("troops", []))):
            keys.append(f"troops.slot_{i + 1}")
        if self.army.get("siege", {}).get("name"):
            keys.append("troops.siege")
        for i in range(len(self.army.get("heroes", []))):
            keys.append(f"troops.hero_{i + 1}")
        return keys or ["(none configured)"]

    def resolve_slot(self, key: str) -> dict | None:
        """Resolve a "context.name" key to its slot dict, or None."""
        if "." not in key:
            return None
        ctx, name = key.split(".", 1)

        if ctx in self.buttons and name in self.buttons[ctx]:
            return self.buttons[ctx][name]

        if ctx == "troops":
            if name == "siege":
                return self.army.get("siege")
            if name.startswith("slot_"):
                try:
                    idx = int(name.split("_")[1]) - 1
                    troops = self.army.get("troops", [])
                    return troops[idx] if 0 <= idx < len(troops) else None
                except (ValueError, IndexError):
                    return None
            if name.startswith("hero_"):
                try:
                    idx = int(name.split("_")[1]) - 1
                    heroes = self.army.get("heroes", [])
                    return heroes[idx] if 0 <= idx < len(heroes) else None
                except (ValueError, IndexError):
                    return None
        return None

    # ── Internal helpers ──────────────────────────────────────────────────

    def _read(self, key: str, default: Any) -> Any:
        path = self._paths[key]
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
            return default
        except Exception:
            return default

    def _write(self, key: str, data: Any):
        self._paths[key].write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
