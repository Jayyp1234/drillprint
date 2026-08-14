"""Library build: full A11 sweep → fingerprints → versioned store (M3, §21).

    python -m synth.build_library --db data/library.db --version v1 [--subset N]

Library seeds are the 0-series (benchmark/scenario queries use disjoint
1000+-series seeds, A19.3). Every episode is fingerprinted under each
PIPELINE whose channels it carries; relabeled stick-slip corners enter as
NORMAL_DRILLING (A4.3) and are listed in the build report.
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

from engine.hashing import hash_constellation
from engine.order_domain import align_rpm, resample_to_order_domain
from engine.peaks import find_peaks
from engine.stft import frame_count, log_magnitude, stft_mag
from engine.types import PROFILES
from store.fingerprint_db import PIPELINES, FingerprintDB
from synth import bit_bounce, normal, stick_slip, whirl
from synth.common import SynthEpisode

LIB_SEED = 0
LOW_DEEP_F0_HZ = 0.12  # A1: predicted f0 below this selects LOW_DEEP


def _stick_slip_profile(ep: SynthEpisode) -> str:
    t_model = ep.params.get("t_model_s")
    if t_model and 1.0 / t_model < LOW_DEEP_F0_HZ:
        return "LOW_DEEP"
    return "LOW"


def fingerprint_channel(
    ep: SynthEpisode, channel: str, profile_name: str, domain: str,
    band: tuple[int, int],
) -> tuple[list[tuple[int, int]], int]:
    """One (episode, channel, pipeline) fingerprinting pass → (hashes, n_frames)."""
    profile = PROFILES[profile_name]
    ch = ep.channels[channel]
    if domain == "order":
        rpm = ep.channels["RPM_SURF"]
        aligned = align_rpm(rpm.samples, rpm.fs, len(ch.samples), ch.fs)
        x = resample_to_order_domain(ch.samples, ch.fs, aligned)
    else:
        x = ch.samples
    peaks = find_peaks(
        log_magnitude(stft_mag(x, profile)),
        neighborhood=profile.peak_neighborhood,
        band=band,
        persistence_frac=profile.persistence_frac,
    )
    return hash_constellation(peaks, profile), frame_count(len(x), profile)


def fingerprint_episode(ep: SynthEpisode) -> tuple[list, list]:
    """All applicable pipelines → (fingerprint rows, per-profile stats rows)."""
    fingerprints: list[tuple[int, str, str, str, int]] = []
    per_profile: dict[str, dict] = {}
    for cfg in PIPELINES.values():
        present = [c for c in cfg["channels"] if c in ep.channels]
        if not present:
            continue
        profile_name = cfg["profile"]
        if profile_name == "LOW":
            profile_name = _stick_slip_profile(ep)
        for channel in present:
            hashes, n_frames = fingerprint_channel(
                ep, channel, profile_name, cfg["domain"], cfg["band"]
            )
            fingerprints.extend(
                (h, channel, profile_name, cfg["domain"], t) for h, t in hashes
            )
            agg = per_profile.setdefault(
                profile_name, {"n_frames": n_frames, "hashes": []}
            )
            agg["n_frames"] = max(agg["n_frames"], n_frames)
            agg["hashes"].extend(h for h, _ in hashes)
    stats = [
        (name, agg["n_frames"], len(agg["hashes"]), len(set(agg["hashes"])))
        for name, agg in sorted(per_profile.items())
    ]
    return fingerprints, stats


def iter_episodes(subset: int | None = None):
    """The full A11 sweep (176 episodes), library-seeded; optionally truncated."""
    gens = itertools.chain(
        (stick_slip.generate(**p) for p in stick_slip.sweep()),
        (whirl.generate(**p, seed=LIB_SEED) for p in whirl.sweep()),
        (bit_bounce.generate(**p, seed=LIB_SEED) for p in bit_bounce.sweep()),
        (normal.generate(**p, seed=LIB_SEED) for p in normal.sweep()),
    )
    return itertools.islice(gens, subset) if subset else gens


def build(db_path: str | Path, version: str, subset: int | None = None) -> dict:
    t0 = time.perf_counter()
    db = FingerprintDB(db_path)
    db.create_library(version, notes=f"synthetic sweep, subset={subset or 'full'}")
    relabeled: list[str] = []
    n_eps = 0
    for ep in iter_episodes(subset):
        fingerprints, stats = fingerprint_episode(ep)
        db.add_episode(
            version, ep.slug, ep.dysfunction_class, ep.duration_s, ep.params,
            [(name, ch.fs) for name, ch in ep.channels.items()],
            fingerprints, stats,
        )
        if ep.diagnostics.get("relabeled"):
            relabeled.append(ep.slug)
        n_eps += 1
    elapsed = time.perf_counter() - t0
    report = {
        "version": version,
        "build_seconds": round(elapsed, 1),
        "episodes": n_eps,
        "relabeled_to_normal": relabeled,
        **db.stats(version),
    }
    db.close()
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/library.db")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--subset", type=int, default=None)
    args = ap.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    report = build(args.db, args.version, args.subset)
    report_path = Path(args.db).parent / f"build_report_{args.version}.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"report -> {report_path}")


if __name__ == "__main__":
    main()
