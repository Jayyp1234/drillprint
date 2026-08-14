"""Canonical channel registry (spec §16 / A10)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    uom: str
    fs: float
    mnemonic: str
    profiles: tuple[str, ...]
    observes: tuple[str, ...]
    badge: str | None = None


REGISTRY: dict[str, ChannelSpec] = {
    "TORQUE_SURF": ChannelSpec(
        "TORQUE_SURF", "kN.m", 10.0, "TQA",
        ("LOW", "LOW_DEEP"), ("STICK_SLIP",),
    ),
    "RPM_SURF": ChannelSpec(
        "RPM_SURF", "rpm", 10.0, "RPMA", ("LOW",), (),
    ),
    "RPM_DH": ChannelSpec(
        "RPM_DH", "rpm", 10.0, "RPMB",
        ("LOW", "LOW_DEEP"), ("STICK_SLIP",),
    ),
    "ACC_LAT_X": ChannelSpec(
        "ACC_LAT_X", "g", 400.0, "ALX",
        ("HIGH", "ORDER"), ("WHIRL_BACKWARD", "WHIRL_FORWARD"),
    ),
    "ACC_LAT_Y": ChannelSpec(
        "ACC_LAT_Y", "g", 400.0, "ALY",
        ("HIGH", "ORDER"), ("WHIRL_BACKWARD", "WHIRL_FORWARD"),
    ),
    "ACC_AX": ChannelSpec(
        "ACC_AX", "g", 100.0, "AXZ",
        ("MID", "ORDER"), ("BIT_BOUNCE",),
    ),
    "WOB": ChannelSpec(
        "WOB", "kN", 10.0, "WOBA", ("LOW",), ("BIT_BOUNCE",),
        badge="partial band — not matchable",
    ),
    "HOOKLOAD": ChannelSpec(
        "HOOKLOAD", "kN", 10.0, "HKLA", ("LOW",), (),
    ),
    "BIT_DEPTH": ChannelSpec(
        "BIT_DEPTH", "m", 1.0, "DBTM", ("LOW_DECIM",), (),
    ),
    "HOLE_DEPTH": ChannelSpec(
        "HOLE_DEPTH", "m", 1.0, "DMEA", ("LOW_DECIM",), (),
    ),
    "BLOCK_POS": ChannelSpec(
        "BLOCK_POS", "m", 1.0, "BPOS", ("LOW_DECIM",), (),
    ),
}


def observability_badges(channel: str) -> dict:
    """Band-aware badges for the Monitor channel rail (gate 4 backend)."""
    spec = REGISTRY.get(channel)
    if spec is None:
        return {"channel": channel, "observes": [], "badge": "unknown channel"}
    rig = channel in (
        "RPM_SURF", "HOOKLOAD", "BIT_DEPTH", "HOLE_DEPTH", "BLOCK_POS",
    )
    return {
        "channel": channel,
        "fs": spec.fs,
        "observes": list(spec.observes),
        "badge": spec.badge,
        "entirely_blind": len(spec.observes) == 0 and not rig,
    }
