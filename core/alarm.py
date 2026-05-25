"""
Alarm manager — alerts the user when the bot detects a problem,
then waits for mouse movement before letting execution continue.

Used by DETECT and SCROLL_SEARCH steps whose on_fail policy is ALARM_WAIT.
Uses only winsound (stdlib) — no extra pip packages needed.
"""

import threading
import time
import winsound

from pynput import mouse as pynput_mouse


class AlarmManager:
    """
    Non-blocking alarm: plays alternating beep tones in a background thread
    until either the user moves the mouse or stop() is called externally.

    Typical usage (from a bot execution thread):

        alarm = AlarmManager()
        alarm.trigger()                         # starts beeping immediately
        alarm.wait(stop_signal=self._stop_flag) # block until resolved
        # execution resumes here
    """

    # Beep pattern — two alternating tones (Hz, ms) repeated while active
    _TONES = [(1047, 160), (784, 160)]   # C6 / G5

    def __init__(self):
        self._active  = threading.Event()   # set while alarm is sounding
        self._resolved = threading.Event()  # set when alarm ends (any reason)

    # ── Public API ────────────────────────────────────────────────────────

    def trigger(self):
        """
        Start the alarm immediately (non-blocking).
        Spawns a beep thread and a mouse-watcher thread.
        Resets internal state so trigger() can be called multiple times.
        """
        self._active.clear()
        self._resolved.clear()
        self._active.set()

        threading.Thread(target=self._beep_loop,   daemon=True).start()
        threading.Thread(target=self._mouse_watch, daemon=True).start()

    def wait(self, stop_signal: threading.Event | None = None):
        """
        Block the calling thread until the alarm is resolved.

        Parameters
        ----------
        stop_signal : threading.Event, optional
            If this event becomes set the alarm is force-stopped and
            wait() returns (so the bot can honour a Stop request even
            while the alarm is playing).
        """
        while not self._resolved.is_set():
            if stop_signal is not None and stop_signal.is_set():
                self.stop()
                break
            time.sleep(0.05)

    def stop(self):
        """
        Force-stop the alarm (e.g. when the user clicks Stop in the UI
        while an alarm is active).
        """
        self._active.clear()
        self._resolved.set()

    @property
    def is_active(self) -> bool:
        return self._active.is_set()

    # ── Internal ──────────────────────────────────────────────────────────

    def _beep_loop(self):
        """Alternating tone pattern — runs until _active is cleared."""
        while self._active.is_set():
            for freq, dur in self._TONES:
                if not self._active.is_set():
                    break
                try:
                    winsound.Beep(freq, dur)
                except Exception:
                    break
            time.sleep(0.18)

    def _mouse_watch(self):
        """
        pynput mouse listener — stops the alarm on the first mouse move.
        Returns False to unregister itself after one event.
        """
        def _on_move(x, y):
            if self._active.is_set():
                self._active.clear()
                self._resolved.set()
            return False  # tell pynput to stop this listener

        listener = pynput_mouse.Listener(on_move=_on_move)
        listener.daemon = True
        listener.start()
        # keep the thread alive until the listener dies
        listener.join()
