"""Naïve band-energy baseline detector (A19 / §14) — the honest incumbent."""

from __future__ import annotations

import numpy as np

from engine.sssi import band_energy_rms, sssi


class BandEnergyBaseline:
    """Per-class band-pass RMS + threshold; thresholds frozen after calibration."""

    def __init__(self, thresholds: dict[str, float] | None = None):
        self.thresholds = thresholds or {
            "STICK_SLIP": 0.2,
            "WHIRL_BACKWARD": 0.1,
            "BIT_BOUNCE": 0.08,
        }

    def evaluate_window(
        self,
        class_name: str,
        x: np.ndarray,
        fs: float,
        f0_hz: float | None = None,
    ) -> bool:
        thr = self.thresholds[class_name]
        if class_name == "STICK_SLIP":
            return sssi(x, fs, f0_hz or 0.25) >= thr
        if class_name == "WHIRL_BACKWARD":
            return band_energy_rms(x, fs, (5.0, 50.0)) >= thr
        if class_name == "BIT_BOUNCE":
            return band_energy_rms(x, fs, (1.0, 20.0)) >= thr
        return False

    # (class → (bound channel, window s, hop s)) for whole-run scanning
    SCAN = {
        "STICK_SLIP": ("TORQUE_SURF", 20.0, 5.0),
        "WHIRL_BACKWARD": ("ACC_LAT_X", 4.0, 2.0),
        "BIT_BOUNCE": ("ACC_AX", 4.0, 2.0),
    }
    REFRACTORY_S = 30.0  # one alert per sustained excursion, not per hop

    def scan(self, channels: dict, t_end: float) -> list[tuple[str, float]]:
        """Slide over the WHOLE run and emit (class, t) alerts on upward
        threshold crossings (H1 fix: the baseline is scored on exactly the
        same alert-stream contract as DrillPrint — false positives on normal
        data count against it, late detections score by the same T_tol)."""
        alerts: list[tuple[str, float]] = []
        for cls, (ch_name, win_s, hop_s) in self.SCAN.items():
            ch = channels.get(ch_name)
            if ch is None:
                continue
            x, fs = ch.samples, ch.fs
            win, hop = int(win_s * fs), int(hop_s * fs)
            prev, last_alert = False, -1e9
            for i in range(win, len(x) + 1, hop):
                t = i / fs
                if t > t_end:
                    break
                hit = self.evaluate_window(cls, x[i - win:i], fs)
                if hit and not prev and t - last_alert >= self.REFRACTORY_S:
                    alerts.append((cls, t))
                    last_alert = t
                prev = hit
        return sorted(alerts, key=lambda a: a[1])
