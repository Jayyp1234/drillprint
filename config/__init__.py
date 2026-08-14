"""Well-context config loader (A13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class WellConfig:
    name: str
    length_m: float
    n_blades: int
    d_hole_m: float
    d_bit_m: float
    bit_depth_m: float
    hole_depth_m: float
    block_pos_m: float = 12.3
    string_weight_kn: float = 1022.0
    channels: tuple[str, ...] = field(default_factory=tuple)

    @property
    def clearance_m(self) -> float:
        return 0.5 * (self.d_hole_m - self.d_bit_m)


def load_well(path: str | Path | None = None) -> WellConfig:
    """Load a well-context YAML; default is config/well01.yaml."""
    if path is None:
        path = Path(__file__).parent / "well01.yaml"
    data = yaml.safe_load(Path(path).read_text())
    return WellConfig(
        name=data["name"],
        length_m=float(data["length_m"]),
        n_blades=int(data["n_blades"]),
        d_hole_m=float(data["d_hole_m"]),
        d_bit_m=float(data["d_bit_m"]),
        bit_depth_m=float(data.get("bit_depth_m", data["length_m"])),
        hole_depth_m=float(data.get("hole_depth_m", data["length_m"])),
        block_pos_m=float(data.get("block_pos_m", 12.3)),
        string_weight_kn=float(data.get("string_weight_kn", 1022.0)),
        channels=tuple(data.get("channels", ())),
    )
