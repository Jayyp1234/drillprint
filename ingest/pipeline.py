"""Streaming evaluation engine — matcher schedule, K=2 debounce, twin_state (M4).

Data-time driven (no wall clock in the data plane). Call ``advance_to(t)`` after
ingesting frames; the engine emits monitor messages up through stream time ``t``.
"""

from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from config import WellConfig, load_well
from engine.hashing import hash_constellation
from engine.order_domain import OrderDomainInvalid, resample_to_order_domain
from engine.peaks import find_peaks
from engine.sssi import band_energy_rms, sssi
from engine.stft import frame_count, log_magnitude, stft_mag
from engine.twin_kinematics import TwinKinematics, twist_rad
from engine.types import PROFILES
from ingest.sessions import Session
from store.fingerprint_db import PIPELINES, FingerprintDB
from store.query import ClassMatcher

K_DEBOUNCE = 2
TWIN_CADENCE_S = 0.040  # 40 ms of data-time (§24)
SPECTRAL_DB_FLOOR, SPECTRAL_DB_CEIL = -80.0, 0.0


@dataclass
class ActiveDetection:
    class_name: str
    tier: int
    confidence: float
    p_corr: float
    score: int
    sssi: float | None = None
    episode_id: str | None = None
    distinct_matched: int = 0

    def as_dict(self) -> dict:
        d = {
            "class": self.class_name,
            "tier": self.tier,
            "confidence": self.confidence,
            "p_corr": self.p_corr,
            "score": self.score,
        }
        if self.sssi is not None:
            d["sssi"] = self.sssi
        if self.episode_id is not None:
            d["episode"] = self.episode_id
        if self.distinct_matched:
            d["distinct_matched"] = self.distinct_matched
        return d


@dataclass
class DebounceState:
    streak: int = 0
    last_eval_t: float = -np.inf
    last_window_end: float = -np.inf
    confirmed: bool = False
    best: ActiveDetection | None = None


class StreamEngine:
    """Owns session + matchers + emission. Pure data-time (A14/A20)."""

    def __init__(
        self,
        db: FingerprintDB,
        well: WellConfig | None = None,
        mode: str = "replay",
        library_version: str | None = None,
        tier1_thresholds: dict[str, float] | None = None,
        emit: Callable[[dict], None] | None = None,
    ):
        self.session = Session(mode=mode)
        self.db = db
        self.well = well or load_well()
        self.version = library_version or db.active_version()
        self.emit = emit or (lambda _m: None)
        self.messages: list[dict] = []
        self.kin = TwinKinematics(n_blades=self.well.n_blades)
        self.f0_hz = self._predict_f0()
        self.tier1 = tier1_thresholds or {
            "STICK_SLIP": 0.15,
            "WHIRL_BACKWARD": 0.08,
            "BIT_BOUNCE": 0.05,
        }
        self.matchers = {
            cls: ClassMatcher(db, cls, library_version=self.version)
            for cls in PIPELINES
        }
        # Override stick-slip profile to LOW_DEEP when needed
        if self._predict_f0() < 0.12:
            self.matchers["STICK_SLIP"] = ClassMatcher(
                db, "STICK_SLIP", profile_name="LOW_DEEP", library_version=self.version
            )
        self._debounce: dict[str, DebounceState] = defaultdict(DebounceState)
        self._next_eval: dict[str, float] = {
            cls: 0.0 for cls in PIPELINES
        }
        self._next_twin_t = 0.0
        self._active: dict[str, ActiveDetection] = {}
        self._last_twin_t = 0.0
        self._spectral_emitted: dict[tuple[str, str], int] = defaultdict(int)

    def _predict_f0(self) -> float:
        from engine.twin_kinematics import torsional_stiffness_at
        import math
        k = torsional_stiffness_at(self.well.length_m)
        j_b = 200.0  # reference BHA inertia for prior
        return 1.0 / (2.0 * math.pi * math.sqrt(j_b / k))

    def ingest_frame(self, name: str, t0: float, values, fs: float | None = None) -> dict:
        ack = self.session.ingest(name, t0, values, fs)
        if ack.get("ack"):
            self.advance_to(self.session.stream_end())
        return ack

    def _push(self, msg: dict) -> None:
        self.messages.append(msg)
        self.emit(msg)

    def advance_to(self, t: float) -> None:
        """Run all due evaluations and twin ticks up through data-time ``t``."""
        while self._next_twin_t <= t + 1e-12:
            self._emit_twin(self._next_twin_t)
            self._next_twin_t += TWIN_CADENCE_S
        for cls, matcher in self.matchers.items():
            profile = PROFILES[matcher.profile_name]
            cadence = profile.eval_cadence
            # ORDER cadence is in revolutions — convert via current RPM
            if profile.domain == "order":
                rpm = self.session.sample_at("RPM_SURF", t, 120.0)
                cadence_s = cadence * 60.0 / max(rpm, 10.0)
            else:
                cadence_s = cadence
            while self._next_eval[cls] <= t + 1e-12:
                # Don't consume the eval slot until every needed channel has
                # actually delivered data covering it — advance_to(t) can fire
                # off one channel's block while another still lags a block
                # behind, and a consumed-but-empty eval is lost forever (this
                # silently killed every stick-slip Tier-2: the 120 s window
                # returned None at trigger time, then was never retried).
                te = self._next_eval[cls]
                needed = [PIPELINES[cls]["primary"]]
                if profile.domain == "order":
                    needed.append("RPM_SURF")
                ready = all(
                    (b := self.session.buffers.get(ch)) is not None
                    and b.last_end is not None
                    and b.last_end >= te - 0.5 / b.fs
                    for ch in needed
                )
                if not ready:
                    break  # retry at the same data-time on the next advance
                self._evaluate_class(cls, matcher, te)
                self._next_eval[cls] += cadence_s
        self._emit_tier1(t)
        self._emit_spectral(t)

    def _window_span(self, matcher: ClassMatcher, t_end: float) -> tuple[float, float] | None:
        profile = PROFILES[matcher.profile_name]
        if profile.domain == "order":
            # W in revolutions → approximate seconds via recent mean RPM
            rpm = self.session.sample_at("RPM_SURF", t_end, 120.0)
            win_s = profile.window_w * 60.0 / max(rpm, 10.0)
        else:
            win_s = float(profile.window_w)
        t0 = t_end - win_s
        if t0 < 0:
            return None
        return t0, t_end

    def _evaluate_class(self, cls: str, matcher: ClassMatcher, t_end: float) -> None:
        span = self._window_span(matcher, t_end)
        if span is None:
            return
        t0, t1 = span
        if self.session.overlaps_skip(t0, t1):
            return
        profile = PROFILES[matcher.profile_name]
        primary = PIPELINES[cls]["primary"]
        channels = [c for c in matcher.channels if c in self.session.buffers]
        if primary not in channels:
            return
        if profile.domain == "order":
            if "RPM_SURF" not in self.session.buffers:
                return
            win = self.session.get_window(
                [primary, "RPM_SURF"], (t0, t1), align_to=primary
            )
            if win is None:
                return
            try:
                x = resample_to_order_domain(win[primary], self.session.buffers[primary].fs, win["RPM_SURF"])
            except OrderDomainInvalid:
                return
        else:
            win = self.session.get_window([primary], (t0, t1))
            if win is None:
                return
            x = win[primary]

        peaks = find_peaks(
            log_magnitude(stft_mag(x, profile)),
            neighborhood=profile.peak_neighborhood,
            band=matcher.band,
            persistence_frac=profile.persistence_frac,
        )
        hashes = hash_constellation(peaks, profile)
        n_frames = frame_count(len(x), profile)
        if n_frames < 2 or not hashes:
            return

        # constellation message
        self._push({
            "type": "constellation",
            "t": t1,
            "channel": primary,
            "profile": matcher.profile_name,
            "domain": matcher.domain,
            "peaks": [
                {"t": t0 + (p.m * profile.hop + profile.n / 2) / (
                    profile.rate if profile.domain == "time"
                    else (self.session.sample_at("RPM_SURF", t1, 120.0) / 60.0 * profile.rate)
                ), "bin": p.k, "mag_db": p.mag_db}
                for p in peaks[:40]
            ],
        })

        results = matcher.evaluate(hashes, n_frames)
        deb = self._debounce[cls]
        hop_s = (
            profile.hop / profile.rate if profile.domain == "time"
            else profile.hop / 64.0 * 60.0 / max(
                self.session.sample_at("RPM_SURF", t1, 120.0), 10.0
            )
        )
        fresh = (t1 - deb.last_window_end) >= hop_s - 1e-9

        if not results:
            if fresh:
                deb.streak = 0
            return
        best = results[0]
        # §5 absorption: only fire when the WINNING episode is this class —
        # a normal-baseline win means healthy drilling, however confident.
        fired = (best.alert or best.geom_alert) and (
            matcher.episode_class.get(best.episode_id) == cls
        )
        if not fired:
            if fresh:
                deb.streak = 0
                # E6a: re-arm the one-shot confirm latch — without this a
                # class could emit at most ONE tier-2 detection per engine
                # lifetime, so an early spurious confirm permanently silenced
                # the genuine event (bench forensics 2026-08-11: FP+FN pairs).
                deb.confirmed = False
                deb.best = None
                if cls in self._active and self._active[cls].tier == 2:
                    del self._active[cls]
            return

        # K=2: second confident evaluation must contain ≥ 1 hop of new data (A2).
        if deb.streak == 0:
            deb.streak = 1
        elif fresh:
            deb.streak += 1
        deb.last_eval_t = t1
        deb.last_window_end = t1

        p_disp = (
            best.p_corr if best.p_geom_corr is None
            else min(best.p_corr, best.p_geom_corr)
        )
        det = ActiveDetection(
            class_name=cls,
            tier=2 if deb.streak >= K_DEBOUNCE else 1,
            confidence=best.confidence,
            p_corr=p_disp,
            score=max(best.score, best.distinct_matched),
            episode_id=best.episode_id,
            distinct_matched=best.distinct_matched,
            sssi=None,
        )
        if cls == "STICK_SLIP":
            torque = self.session.get_window(["TORQUE_SURF"], (max(0, t1 - 30), t1))
            if torque is not None:
                det.sssi = sssi(torque["TORQUE_SURF"], 10.0, self._predict_f0())

        if deb.streak >= K_DEBOUNCE:
            if not deb.confirmed:
                deb.confirmed = True
                deb.best = det
                self._active[cls] = det
                self._push({
                    "type": "detection",
                    "t": t1,
                    "class": cls,
                    "tier": 2,
                    "episode": best.episode_id,
                    "confidence": best.confidence,
                    "score": best.score,
                    "distinct_matched": best.distinct_matched,
                    "lambda": best.lam,
                    "lambda_geom": best.lam_geom,
                    "p_corr": best.p_corr,
                    "p_geom_corr": best.p_geom_corr,
                    "delta_star": best.delta_star,
                    "histogram": {
                        str(k): v for k, v in list(best.histogram.items())[:64]
                    },
                    "sssi": det.sssi,
                    "library_version": self.version,
                    "diag": {},
                })
            else:
                self._active[cls] = det

    def _emit_tier1(self, t: float) -> None:
        """Band-energy / SSSI advisories (A2) — amber only, never motion."""
        # Stick-slip SSSI
        torque = self.session.get_window(
            ["TORQUE_SURF"], (max(0.0, t - max(2.0 / max(self._predict_f0(), 0.05), 10.0)), t)
        )
        if torque is not None and len(torque["TORQUE_SURF"]) >= 16:
            val = sssi(torque["TORQUE_SURF"], 10.0, self._predict_f0())
            if val >= self.tier1["STICK_SLIP"] and "STICK_SLIP" not in self._active:
                det = ActiveDetection(
                    "STICK_SLIP", 1, min(0.99, val), 1.0, 0, sssi=val
                )
                self._active["STICK_SLIP"] = det
                self._push({
                    "type": "detection",
                    "t": t,
                    "class": "STICK_SLIP",
                    "tier": 1,
                    "confidence": det.confidence,
                    "score": 0,
                    "p_corr": 1.0,
                    "sssi": val,
                    "library_version": self.version,
                })
            elif val < self.tier1["STICK_SLIP"] * 0.7:
                cur = self._active.get("STICK_SLIP")
                if cur and cur.tier == 1:
                    del self._active["STICK_SLIP"]

        # Whirl band energy on ACC_LAT_X (5–50 Hz display band proxy)
        if "ACC_LAT_X" in self.session.buffers:
            win = self.session.get_window(
                ["ACC_LAT_X"], (max(0.0, t - 2.0), t)
            )
            if win is not None and len(win["ACC_LAT_X"]) >= 64:
                e = band_energy_rms(win["ACC_LAT_X"], 400.0, (5.0, 50.0))
                if e >= self.tier1["WHIRL_BACKWARD"] and "WHIRL_BACKWARD" not in self._active:
                    self._active["WHIRL_BACKWARD"] = ActiveDetection(
                        "WHIRL_BACKWARD", 1, min(0.99, e), 1.0, 0
                    )
                    self._push({
                        "type": "detection", "t": t, "class": "WHIRL_BACKWARD",
                        "tier": 1, "confidence": min(0.99, e), "score": 0,
                        "p_corr": 1.0, "library_version": self.version,
                    })

        if "ACC_AX" in self.session.buffers:
            win = self.session.get_window(["ACC_AX"], (max(0.0, t - 2.0), t))
            if win is not None and len(win["ACC_AX"]) >= 32:
                e = band_energy_rms(win["ACC_AX"], 100.0, (1.0, 20.0))
                if e >= self.tier1["BIT_BOUNCE"] and "BIT_BOUNCE" not in self._active:
                    self._active["BIT_BOUNCE"] = ActiveDetection(
                        "BIT_BOUNCE", 1, min(0.99, e), 1.0, 0
                    )
                    self._push({
                        "type": "detection", "t": t, "class": "BIT_BOUNCE",
                        "tier": 1, "confidence": min(0.99, e), "score": 0,
                        "p_corr": 1.0, "library_version": self.version,
                    })

    def _emit_spectral(self, t: float) -> None:
        """Emit new STFT columns as spectral_frame messages."""
        for name, buf in self.session.buffers.items():
            from ingest.channels import REGISTRY
            spec = REGISTRY.get(name)
            if not spec:
                continue
            for pname in spec.profiles:
                profile = PROFILES[pname]
                if profile.domain != "time" or abs(profile.rate - buf.fs) > 1e-9:
                    continue
                # Need at least one full frame ending at/before t
                n_need = profile.n
                if buf.last_end is None or buf.last_end < n_need / buf.fs:
                    continue
                key = (name, pname)
                already = self._spectral_emitted[key]
                # Extract from start of buffer through t
                win = self.session.get_window([name], (0.0, min(t, buf.last_end)))
                if win is None:
                    continue
                mag = log_magnitude(stft_mag(win[name], profile))
                if mag.shape[0] <= already:
                    continue
                for mi in range(already, mag.shape[0]):
                    col = mag[mi]
                    # downsample bins for wire (keep ≤ 128)
                    if len(col) > 128:
                        idx = np.linspace(0, len(col) - 1, 128).astype(int)
                        col = col[idx]
                    q = np.clip(
                        (col - SPECTRAL_DB_FLOOR)
                        / (SPECTRAL_DB_CEIL - SPECTRAL_DB_FLOOR)
                        * 255.0,
                        0, 255,
                    ).astype(np.uint8)
                    frame_t = (mi * profile.hop + profile.n / 2) / profile.rate
                    self._push({
                        "type": "spectral_frame",
                        "t": frame_t,
                        "channel": name,
                        "profile": pname,
                        "db_floor": SPECTRAL_DB_FLOOR,
                        "db_ceil": SPECTRAL_DB_CEIL,
                        "data_b64": base64.b64encode(q.tobytes()).decode("ascii"),
                        "n_bins": int(len(q)),
                    })
                self._spectral_emitted[key] = mag.shape[0]

    def _emit_twin(self, t: float) -> None:
        rpm_s = self.session.sample_at("RPM_SURF", t, 0.0)
        rpm_dh = self.session.sample_at("RPM_DH", t, rpm_s)
        torque = self.session.sample_at("TORQUE_SURF", t, 0.0)
        wob = self.session.sample_at("WOB", t, 0.0)
        hook = self.session.sample_at("HOOKLOAD", t, self.well.string_weight_kn - wob)
        bit_d = self.session.sample_at("BIT_DEPTH", t, self.well.bit_depth_m)
        hole_d = self.session.sample_at("HOLE_DEPTH", t, self.well.hole_depth_m)
        block = self.session.sample_at("BLOCK_POS", t, self.well.block_pos_m)

        whirl_det = self._active.get("WHIRL_BACKWARD")
        bounce_det = self._active.get("BIT_BOUNCE")
        whirl_active = bool(whirl_det and whirl_det.tier == 2)
        bounce_active = bool(bounce_det and bounce_det.tier == 2)
        dt = t - self._last_twin_t if t > self._last_twin_t else TWIN_CADENCE_S
        w_phase, b_phase = self.kin.step(dt, rpm_s, whirl_active, bounce_active)
        self._last_twin_t = t

        try:
            tw = twist_rad(torque, max(bit_d, 1.0))
        except ValueError:
            tw = 0.0

        ecc = 0.0
        order = None
        if whirl_active:
            ecc = min(1.0, 0.3 * (whirl_det.confidence if whirl_det else 0.0))
            order = float(self.well.n_blades + 1)

        amp_mm = 0.0
        if bounce_active and bounce_det:
            amp_mm = 2.0 * bounce_det.confidence

        self._push({
            "type": "twin_state",
            "t": round(t, 5),
            "bit_depth_m": bit_d,
            "hole_depth_m": hole_d,
            "rpm_surface": rpm_s,
            "rpm_downhole": rpm_dh,
            "torque_knm": torque,
            "wob_kn": wob,
            "hookload_kn": hook,
            "twist_rad": tw,
            "block_pos_m": block,
            "active_detections": [d.as_dict() for d in self._active.values()],
            "whirl": {
                "active": whirl_active,
                "order": order,
                "phase_rad": w_phase,
                "eccentricity": ecc,
            },
            "bounce": {
                "active": bounce_active,
                "amp_mm": amp_mm,
                "phase_rad": b_phase,
            },
        })

    def detections(self, tier: int | None = None) -> list[dict]:
        out = [m for m in self.messages if m.get("type") == "detection"]
        if tier is not None:
            out = [m for m in out if m.get("tier") == tier]
        return out

    def twin_log(self) -> list[dict]:
        return [m for m in self.messages if m.get("type") == "twin_state"]
