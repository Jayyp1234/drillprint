"""Pure twin-state kinematics (spec §24 / A5 / A8).

twist_rad = torque / k with k = G·J_p / L (L = current bit depth).
Whirl orbit phase integrates Ω_orbit = −N_b · ω (inertial frame — NOT the
sensor-frame line at order N_b+1 that fingerprints hash).
Bounce phase integrates from axial content / RPM.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Mirror of synth.common steel/pipe constants — engine must not import synth.
G_STEEL = 79.6e9  # Pa
D_OUTER, D_INNER = 0.127, 0.1086  # m
J_PIPE = (math.pi / 32.0) * (D_OUTER**4 - D_INNER**4)


def torsional_stiffness_at(bit_depth_m: float) -> float:
    """k = G·J_p / L at the current bit depth (A8).

    >>> round(torsional_stiffness_at(3014.1), 2)
    313.85
    """
    if bit_depth_m <= 0:
        raise ValueError("bit_depth_m must be positive")
    return G_STEEL * J_PIPE / bit_depth_m


def twist_rad(torque_knm: float, bit_depth_m: float) -> float:
    """Elastic wind-up angle [rad] = T / k.

    >>> round(twist_rad(14.8, 3014.1), 2)
    47.16
    """
    return (torque_knm * 1000.0) / torsional_stiffness_at(bit_depth_m)


@dataclass
class TwinKinematics:
    """Stateful integrator for whirl/bounce phases across twin_state ticks."""

    n_blades: int = 5
    whirl_phase_rad: float = 0.0
    bounce_phase_rad: float = 0.0

    def step(
        self,
        dt_s: float,
        rpm_surface: float,
        whirl_active: bool = False,
        bounce_active: bool = False,
    ) -> tuple[float, float]:
        """Advance phases by ``dt_s`` of data-time; return (whirl, bounce) phases.

        Ω_orbit = −N_b · ω with ω in rad/s from surface RPM (A5).
        Bounce uses the tricone 3× shaft rate when active.
        """
        omega = rpm_surface * (2.0 * 3.141592653589793 / 60.0)
        if whirl_active and dt_s > 0:
            self.whirl_phase_rad += (-self.n_blades * omega) * dt_s
        if bounce_active and dt_s > 0:
            self.bounce_phase_rad += (3.0 * omega) * dt_s
        return self.whirl_phase_rad, self.bounce_phase_rad
