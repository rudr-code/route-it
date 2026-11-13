"""Optimization profiles for Route.it CVRPTW solver (R24).

Implements three distinct operational trade-off profiles:
1. 'cost_focused': Minimize total actual monetary OPEX + Fleet mobilization + SLA cost.
2. 'balanced': Normalized compromise between routing cost and operational time:
   min 0.5 * (Cost / Cost_ref) + 0.5 * (Duration / Duration_ref).
3. 'driver_productivity': Maximize driver active working time / minimize idle waiting:
   min idle_time subject to Cost <= Cost_min * (1 + delta_max).
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

ProfileType = Literal["cost_focused", "balanced", "driver_productivity"]


class OptimizationProfileConfig(BaseModel):
    """Configuration weights and tolerances for multi-objective optimization."""

    profile: ProfileType = Field("cost_focused", description="Selected optimization profile")
    cost_weight: float = Field(0.5, ge=0.0, le=1.0, description="Weight of cost in balanced profile")
    time_weight: float = Field(0.5, ge=0.0, le=1.0, description="Weight of duration in balanced profile")
    max_cost_inflation_pct: float = Field(
        15.0, ge=0.0, description="Allowable percentage increase in cost for driver productivity profile"
    )


def compute_profile_objective(
    cost: float,
    duration: float,
    idle_time: float,
    profile: ProfileType = "cost_focused",
    ref_cost: float = 1000.0,
    ref_duration: float = 3600.0,
    config: OptimizationProfileConfig | None = None,
) -> float:
    """Compute the scalar objective function value according to the chosen profile.

    Args:
        cost: Composite routing cost (distance + fees).
        duration: Cumulative route duration.
        idle_time: Cumulative customer-window waiting time.
        profile: Profile identifier ('cost_focused', 'balanced', 'driver_productivity').
        ref_cost: Reference cost for normalization in balanced profile.
        ref_duration: Reference duration for normalization in balanced profile.
        config: Optional configuration override.

    Returns:
        Scalar objective to be minimized by the solver.
    """
    cfg = config or OptimizationProfileConfig(profile=profile)

    if profile == "cost_focused":
        return float(cost)

    if profile == "balanced":
        safe_ref_cost = max(1.0, ref_cost)
        safe_ref_dur = max(1.0, ref_duration)
        norm_cost = cost / safe_ref_cost
        norm_dur = duration / safe_ref_dur
        return cfg.cost_weight * norm_cost + cfg.time_weight * norm_dur

    if profile == "driver_productivity":
        # Minimize idle waiting time, heavily penalizing cost inflation beyond allowable threshold
        max_allowable_cost = ref_cost * (1.0 + cfg.max_cost_inflation_pct / 100.0)
        cost_excess = max(0.0, cost - max_allowable_cost)
        # 1 second of idle time has weight 1.0; cost excess has steep penalty
        return idle_time + 500.0 * cost_excess

    return float(cost)
