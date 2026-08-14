"""Event scoring per A19 / §14."""

from __future__ import annotations

from dataclasses import dataclass, field


# A2 Tier-2 targets (data-time, from onset) keyed by (class, rpm_bucket, snr_bucket)
# snr_bucket: "10db" | "0db"; rpm_bucket: "ge120" | "60"
TIER2_TARGETS_S = {
    ("STICK_SLIP", "ref", "10db"): 60.0,
    ("STICK_SLIP", "ref", "0db"): 90.0,
    ("WHIRL_BACKWARD", "ge120", "10db"): 8.0,
    ("WHIRL_BACKWARD", "ge120", "0db"): 15.0,
    ("WHIRL_BACKWARD", "60", "10db"): 16.0,
    ("WHIRL_BACKWARD", "60", "0db"): 30.0,
    ("BIT_BOUNCE", "ge120", "10db"): 12.0,
    ("BIT_BOUNCE", "ge120", "0db"): 20.0,
    ("BIT_BOUNCE", "60", "10db"): 20.0,
    ("BIT_BOUNCE", "60", "0db"): 30.0,
}

# Concrete T_tol from A19 (1.3 × target, rounded up) — asserted ≥ target
T_TOL_S = {
    "STICK_SLIP": 120.0,
    "WHIRL_BACKWARD": 20.0,  # ≥120 RPM; use 40 at 60 RPM via t_tol()
    "BIT_BOUNCE": 26.0,
}


def tier2_target(class_name: str, rpm: float = 120.0, snr_db: float = 10.0) -> float:
    snr_key = "0db" if snr_db <= 0 else "10db"
    if class_name == "STICK_SLIP":
        return TIER2_TARGETS_S[("STICK_SLIP", "ref", snr_key)]
    rpm_key = "60" if rpm < 90 else "ge120"
    return TIER2_TARGETS_S[(class_name, rpm_key, snr_key)]


def t_tol(class_name: str, rpm: float = 120.0, snr_db: float = 10.0) -> float:
    """T_tol = 1.3 × A2 target, rounded up; invariant T_tol ≥ target (A19)."""
    target = tier2_target(class_name, rpm, snr_db)
    if class_name == "STICK_SLIP":
        tol = 120.0
    elif class_name == "WHIRL_BACKWARD":
        tol = 40.0 if rpm < 90 else 20.0
    elif class_name == "BIT_BOUNCE":
        tol = 40.0 if rpm < 90 else 26.0
    else:
        tol = 1.3 * target
    assert tol + 1e-9 >= target, f"T_tol {tol} < A2 target {target}"
    return tol


@dataclass
class Event:
    class_name: str
    onset: float
    offset: float
    rpm: float = 120.0
    snr_db: float = 10.0


@dataclass
class Alert:
    class_name: str
    t: float
    tier: int


@dataclass
class ScoreCard:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    late: int = 0
    latencies: list[float] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> dict:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "late": self.late,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "latency_mean_s": round(sum(self.latencies) / len(self.latencies), 3)
            if self.latencies else None,
            "latencies_s": [round(x, 3) for x in self.latencies],
        }


def score_run(
    events: list[Event],
    alerts: list[Alert],
    tier: int = 2,
) -> dict[str, ScoreCard]:
    """Score Tier-2 (default) alerts against labeled events (A19.1).

    TP = first correct-class alert in [onset, onset+T_tol].
    Late correct-class = FN + late count (never FP).
    Wrong-class or on-normal = FP. One detection credited per event.
    """
    cards: dict[str, ScoreCard] = {}
    used_alerts: set[int] = set()
    tier_alerts = [(i, a) for i, a in enumerate(alerts) if a.tier == tier]

    for ev in events:
        card = cards.setdefault(ev.class_name, ScoreCard())
        tol = t_tol(ev.class_name, ev.rpm, ev.snr_db)
        window = (ev.onset, ev.onset + tol)
        candidates = [
            (i, a) for i, a in tier_alerts
            if a.class_name == ev.class_name and i not in used_alerts
        ]
        # in-window first
        in_win = [(i, a) for i, a in candidates if window[0] - 1e-9 <= a.t <= window[1] + 1e-9]
        if in_win:
            i, a = min(in_win, key=lambda ia: ia[1].t)
            used_alerts.add(i)
            card.tp += 1
            card.latencies.append(a.t - ev.onset)
            continue
        # late correct-class after T_tol but before/at offset+margin
        late = [
            (i, a) for i, a in candidates
            if a.t > window[1] and a.t <= ev.offset + tol
        ]
        if late:
            i, a = min(late, key=lambda ia: ia[1].t)
            used_alerts.add(i)
            card.fn += 1
            card.late += 1
            continue
        card.fn += 1

    # Remaining alerts of scored classes = FP; also any alert on unlabeled time
    labeled_classes = {e.class_name for e in events}
    for i, a in tier_alerts:
        if i in used_alerts:
            continue
        card = cards.setdefault(a.class_name, ScoreCard())
        # Wrong class relative to overlapping event, or alert with no event
        card.fp += 1

    # Ensure all event classes appear
    for ev in events:
        cards.setdefault(ev.class_name, ScoreCard())
    return cards
