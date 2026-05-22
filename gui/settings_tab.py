import logging
import tomllib
from typing import Optional

import customtkinter as ctk

logger = logging.getLogger(__name__)


def _int_or_zero(s: str) -> int:
    try:
        return int(s.strip())
    except ValueError:
        return 0


class SettingsTab(ctk.CTkFrame):
    def __init__(self, parent, adb=None, config: dict = None, config_path: str = "config.toml", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.adb = adb
        self.config = config or {}
        self.config_path = config_path
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        def section(text):
            ctk.CTkLabel(scroll, text=text, font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=6, pady=(12, 2))

        def row(parent, label, default=""):
            f = ctk.CTkFrame(parent)
            f.pack(fill="x", padx=6, pady=3)
            ctk.CTkLabel(f, text=label, width=220, anchor="w").pack(side="left")
            e = ctk.CTkEntry(f, width=280)
            e.insert(0, str(default))
            e.pack(side="left")
            return e

        def toggle_row(parent, label, default=True):
            f = ctk.CTkFrame(parent)
            f.pack(fill="x", padx=6, pady=3)
            ctk.CTkLabel(f, text=label, width=220, anchor="w").pack(side="left")
            var = ctk.BooleanVar(value=default)
            ctk.CTkSwitch(f, text="", variable=var).pack(side="left")
            return var

        adb_cfg = self.config.get("adb", {})
        thresh_cfg = self.config.get("thresholds", {})
        attack_cfg = self.config.get("attack", {})
        notify_cfg = self.config.get("notify", {})
        tess_cfg = self.config.get("tesseract", {})

        section("ADB")
        self._adb_host = row(scroll, "Host", adb_cfg.get("host", "127.0.0.1"))
        self._adb_port = row(scroll, "Port", adb_cfg.get("port", 5555))

        section("Loot Thresholds")
        self._thresh_gold = row(scroll, "Min Gold", thresh_cfg.get("gold", 500000))
        self._thresh_elixir = row(scroll, "Min Elixir", thresh_cfg.get("elixir", 500000))
        self._thresh_dark = row(scroll, "Min Dark Elixir", thresh_cfg.get("dark", 2000))

        section("Attack")
        self._delay_base = row(scroll, "Tap Delay Base (ms)", attack_cfg.get("delay_base_ms", 150))
        self._collect_before = toggle_row(scroll, "Collect before farming", attack_cfg.get("collect_before_farm", True))
        self._heroes_enabled = toggle_row(scroll, "Heroes enabled", attack_cfg.get("heroes_enabled", True))
        self._spells_enabled = toggle_row(scroll, "Spells enabled", attack_cfg.get("spells_enabled", True))

        section("Notifications")
        self._discord_url = row(scroll, "Discord Webhook URL", notify_cfg.get("discord_webhook", ""))
        self._tg_token = row(scroll, "Telegram Bot Token", notify_cfg.get("telegram_token", ""))
        self._tg_chat = row(scroll, "Telegram Chat ID", notify_cfg.get("telegram_chat_id", ""))

        section("Tesseract")
        self._tess_cmd = row(scroll, "Tesseract CMD path", tess_cfg.get("cmd", ""))

        # Action buttons
        btn_frame = ctk.CTkFrame(scroll)
        btn_frame.pack(fill="x", padx=6, pady=12)
        ctk.CTkButton(btn_frame, text="Test ADB Connection", command=self._test_adb).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Test Discord", command=self._test_discord).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Test Telegram", command=self._test_telegram).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Save Settings", fg_color="#1a5c1a", command=self._save).pack(side="right", padx=6)

        self._status_label = ctk.CTkLabel(scroll, text="")
        self._status_label.pack(anchor="w", padx=6, pady=4)

    def _test_adb(self) -> None:
        if self.adb:
            try:
                ok = self.adb.is_connected()
                self._status_label.configure(
                    text="ADB: Connected" if ok else "ADB: Not connected",
                    text_color="#00ff88" if ok else "#ff4444",
                )
            except Exception as exc:
                self._status_label.configure(text=f"ADB error: {exc}", text_color="#ff4444")
        else:
            self._status_label.configure(text="ADB not initialized", text_color="#ffcc00")

    def _test_discord(self) -> None:
        from notify.discord import DiscordNotifier
        url = self._discord_url.get().strip()
        if not url:
            self._status_label.configure(text="No Discord URL set", text_color="#ffcc00")
            return
        try:
            DiscordNotifier(url).send("TASK_STARTED", {"test": "true"})
            self._status_label.configure(text="Discord: test sent", text_color="#00ff88")
        except Exception as exc:
            self._status_label.configure(text=f"Discord error: {exc}", text_color="#ff4444")

    def _test_telegram(self) -> None:
        from notify.telegram import TelegramNotifier
        token = self._tg_token.get().strip()
        chat_id = self._tg_chat.get().strip()
        if not token or not chat_id:
            self._status_label.configure(text="Telegram token/chat not set", text_color="#ffcc00")
            return
        try:
            TelegramNotifier(token, chat_id).send("TASK_STARTED", {"test": "true"})
            self._status_label.configure(text="Telegram: test sent", text_color="#00ff88")
        except Exception as exc:
            self._status_label.configure(text=f"Telegram error: {exc}", text_color="#ff4444")

    def _save(self) -> None:
        config = {
            "adb": {
                "host": self._adb_host.get().strip(),
                "port": _int_or_zero(self._adb_port.get()),
            },
            "thresholds": {
                "gold": _int_or_zero(self._thresh_gold.get()),
                "elixir": _int_or_zero(self._thresh_elixir.get()),
                "dark": _int_or_zero(self._thresh_dark.get()),
            },
            "attack": {
                "delay_base_ms": _int_or_zero(self._delay_base.get()),
                "collect_before_farm": bool(self._collect_before.get()),
                "heroes_enabled": bool(self._heroes_enabled.get()),
                "spells_enabled": bool(self._spells_enabled.get()),
                "strategy": self.config.get("attack", {}).get("strategy", "surround"),
                "troops_per_point": self.config.get("attack", {}).get("troops_per_point", 1),
            },
            "notify": {
                "discord_webhook": self._discord_url.get().strip(),
                "telegram_token": self._tg_token.get().strip(),
                "telegram_chat_id": self._tg_chat.get().strip(),
            },
            "yolo": self.config.get("yolo", {"model_path": "models/coc_yolo.pt", "confidence": 0.6}),
            "tesseract": {"cmd": self._tess_cmd.get().strip()},
        }
        self.config.update(config)
        self._write_toml(config)
        self._status_label.configure(text="Settings saved.", text_color="#00ff88")

    def _write_toml(self, config: dict) -> None:
        lines = []
        for section, values in config.items():
            lines.append(f"[{section}]")
            for k, v in values.items():
                if isinstance(v, str):
                    lines.append(f'{k} = "{v}"')
                elif isinstance(v, bool):
                    lines.append(f"{k} = {'true' if v else 'false'}")
                else:
                    lines.append(f"{k} = {v}")
            lines.append("")
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info("Saved config to %s", self.config_path)
