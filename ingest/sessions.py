"""Per-session ring buffers, gap policy, and aligned-view API (A15).

Ownership: this module alone interpolates RPM onto vibration grids and applies
the ≤1-hop interpolate / >1-hop skip gap policy. order_domain consumes only
aligned pairs returned here.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from engine.types import PROFILES
from ingest.channels import REGISTRY

# A15.5 backpressure: NACK when unprocessed backlog exceeds this.
BACKLOG_LIMIT_S = 30.0
# History retained for query windows (LOW W=120 s, LOW_DEEP W=240 s).
HISTORY_KEEP_S = 300.0


@dataclass
class HealthCounters:
    monotonic_violations: int = 0
    gaps_interpolated: int = 0
    gaps_skipped: int = 0
    backlog_nacks: int = 0
    frames_accepted: int = 0
    frames_dropped: int = 0

    def as_dict(self) -> dict:
        return {
            "monotonic_violations": self.monotonic_violations,
            "gaps_interpolated": self.gaps_interpolated,
            "gaps_skipped": self.gaps_skipped,
            "backlog_nacks": self.backlog_nacks,
            "frames_accepted": self.frames_accepted,
            "frames_dropped": self.frames_dropped,
        }


@dataclass
class ChannelBuffer:
    name: str
    fs: float
    blocks: deque = field(default_factory=deque)  # (t0_stream, values ndarray)
    last_t0: float | None = None
    last_end: float | None = None  # exclusive end time of last accepted block
    skip_until: float = -np.inf  # matcher windows overlapping (gap_start, skip_until) skip
    pending_gaps: list = field(default_factory=list)  # [(t_start, t_end, kind)]

    def duration_s(self) -> float:
        if not self.blocks:
            return 0.0
        t0, vals = self.blocks[0]
        t1, vals1 = self.blocks[-1]
        return (t1 + len(vals1) / self.fs) - t0

    def drop_oldest(self, need_s: float) -> None:
        while self.blocks and self.duration_s() > need_s:
            self.blocks.popleft()


class Session:
    """One ingest/monitor session: ring buffers + stream clock (A14/A15)."""

    def __init__(self, mode: str = "live"):
        if mode not in ("live", "replay"):
            raise ValueError("mode must be 'live' or 'replay'")
        self.mode = mode
        self.buffers: dict[str, ChannelBuffer] = {}
        self.health = HealthCounters()
        self.t0_first: float | None = None  # LIVE epoch latch
        self._skip_regions: list[tuple[float, float]] = []  # data-time gaps > 1 hop

    def _to_stream_t(self, t0_wall: float) -> float:
        if self.mode == "replay":
            return float(t0_wall)
        if self.t0_first is None:
            self.t0_first = float(t0_wall)
        return float(t0_wall) - self.t0_first

    def ingest(
        self,
        name: str,
        t0: float,
        values: list[float] | np.ndarray,
        fs: float | None = None,
    ) -> dict:
        """Accept one batched frame. Returns ack dict (A15.5)."""
        values = np.asarray(values, dtype=np.float64)
        if name not in REGISTRY and fs is None:
            self.health.frames_dropped += 1
            return {"ack": False, "reason": "unknown_channel"}
        fs = float(fs if fs is not None else REGISTRY[name].fs)
        t_stream = self._to_stream_t(t0)

        buf = self.buffers.get(name)
        if buf is None:
            buf = ChannelBuffer(name=name, fs=fs)
            self.buffers[name] = buf
        elif abs(buf.fs - fs) > 1e-9:
            self.health.frames_dropped += 1
            return {"ack": False, "reason": "fs_mismatch"}

        # Monotonic t0 (A15.1)
        if buf.last_t0 is not None and t_stream < buf.last_t0 - 1e-9:
            self.health.monotonic_violations += 1
            self.health.frames_dropped += 1
            return {"ack": False, "reason": "non_monotonic"}

        # Gap policy (A15.2) — hop unit from the channel's primary hashed profile
        if buf.last_end is not None and t_stream > buf.last_end + 1e-9:
            gap_s = t_stream - buf.last_end
            hop_s = self._hop_seconds(name, fs)
            if gap_s <= hop_s + 1e-12:
                # linearly interpolate across the gap
                n_fill = max(1, int(round(gap_s * fs)) - 1)
                if n_fill > 0 and buf.blocks:
                    last_val = float(buf.blocks[-1][1][-1])
                    first_val = float(values[0])
                    fill = np.linspace(last_val, first_val, n_fill + 2)[1:-1]
                    buf.blocks.append((buf.last_end, fill))
                    self.health.gaps_interpolated += 1
            else:
                self.health.gaps_skipped += 1
                self._skip_regions.append((buf.last_end, t_stream))
                buf.pending_gaps.append((buf.last_end, t_stream, "skip"))

        # Backpressure (A15.5): NACK when the buffer holds more than the
        # history window PLUS a 30 s unprocessed backlog. History itself must
        # cover LOW/LOW_DEEP query windows (120–240 s) — that is not backlog.
        if buf.duration_s() > HISTORY_KEEP_S + BACKLOG_LIMIT_S:
            buf.drop_oldest(HISTORY_KEEP_S)
            self.health.backlog_nacks += 1
            self.health.frames_dropped += 1
            return {"ack": False, "reason": "backlog"}

        buf.blocks.append((t_stream, values.copy()))
        buf.last_t0 = t_stream
        buf.last_end = t_stream + len(values) / fs
        # Trim retained history to the query-window budget (no NACK).
        if buf.duration_s() > HISTORY_KEEP_S:
            buf.drop_oldest(HISTORY_KEEP_S)
        self.health.frames_accepted += 1
        return {"ack": True, "t": t_stream, "t_end": buf.last_end}

    def _hop_seconds(self, name: str, fs: float) -> float:
        spec = REGISTRY.get(name)
        if spec and spec.profiles:
            for pname in spec.profiles:
                p = PROFILES[pname]
                if p.domain == "time" and abs(p.rate - fs) < 1e-9:
                    return p.hop / p.rate
        # ORDER hop in seconds depends on RPM; use 0.5 s (1 rev @ 120 RPM) as default
        return 0.5

    def stream_end(self) -> float:
        """Latest data-time present in any buffer."""
        ends = [b.last_end for b in self.buffers.values() if b.last_end is not None]
        return max(ends) if ends else 0.0

    def overlaps_skip(self, t0: float, t1: float) -> bool:
        for a, b in self._skip_regions:
            if t0 < b and t1 > a:
                return True
        return False

    def get_window(
        self,
        channels: list[str] | tuple[str, ...],
        t_span: tuple[float, float],
        align_to: str | None = None,
    ) -> dict[str, np.ndarray] | None:
        """Return time-aligned arrays for ``channels`` over [t0, t1).

        If ``align_to`` is set, all series are interpolated onto that channel's
        native grid (A15.3 — RPM_SURF onto vibration). Returns None if any
        required channel lacks full coverage.
        """
        t0, t1 = t_span
        if t1 <= t0:
            return None
        raw: dict[str, tuple[np.ndarray, np.ndarray]] = {}  # name → (t, x)
        for name in channels:
            pair = self._extract(name, t0, t1)
            if pair is None:
                return None
            raw[name] = pair
        if align_to is None:
            return {n: x for n, (_, x) in raw.items()}
        if align_to not in raw:
            return None
        t_ref, x_ref = raw[align_to]
        out: dict[str, np.ndarray] = {align_to: x_ref}
        fs_ref = self.buffers[align_to].fs
        for name, (t, x) in raw.items():
            if name == align_to:
                continue
            if abs(self.buffers[name].fs - fs_ref) < 1e-9 and len(x) == len(x_ref):
                out[name] = x
            else:
                out[name] = np.interp(t_ref, t, x)
        return out

    def _extract(self, name: str, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray] | None:
        buf = self.buffers.get(name)
        if buf is None or not buf.blocks:
            return None
        # Concatenate covering blocks
        ts: list[np.ndarray] = []
        xs: list[np.ndarray] = []
        for bt0, vals in buf.blocks:
            n = len(vals)
            t = bt0 + np.arange(n) / buf.fs
            mask = (t >= t0 - 0.5 / buf.fs) & (t < t1 + 0.5 / buf.fs)
            if mask.any():
                ts.append(t[mask])
                xs.append(vals[mask])
        if not ts:
            return None
        t = np.concatenate(ts)
        x = np.concatenate(xs)
        # Deduplicate timestamps from abutting blocks
        if len(t) > 1:
            keep = np.concatenate(([True], np.diff(t) > 1e-12))
            t, x = t[keep], x[keep]
        # Require coverage of the span (allow 1-sample edge slack)
        if t[0] > t0 + 1.5 / buf.fs or t[-1] < t1 - 1.5 / buf.fs:
            return None
        # Resample onto a uniform grid at channel fs
        n = max(1, int(round((t1 - t0) * buf.fs)))
        t_grid = t0 + np.arange(n) / buf.fs
        return t_grid, np.interp(t_grid, t, x)

    def latest_sample(self, name: str, default: float = 0.0) -> float:
        buf = self.buffers.get(name)
        if buf is None or not buf.blocks:
            return default
        return float(buf.blocks[-1][1][-1])

    def sample_at(self, name: str, t: float, default: float = 0.0) -> float:
        """Zero-order hold of the latest sample at or before ``t``."""
        buf = self.buffers.get(name)
        if buf is None or not buf.blocks:
            return default
        best = default
        for bt0, vals in buf.blocks:
            for i, v in enumerate(vals):
                ti = bt0 + i / buf.fs
                if ti <= t + 1e-12:
                    best = float(v)
                else:
                    return best
        return best
