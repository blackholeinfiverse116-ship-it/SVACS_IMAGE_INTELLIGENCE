"""
SVACS Operational Risk & Validation Layer package.

This package sits after svacs.runtime.SVACSRuntime in the pipeline:

    Structured Intelligence -> SVACSRuntime (consume/reason/confidence/
    explain/bucket) -> intelligence.vessel_intelligence_engine
    (risk assessment + validation gating) -> Replay -> Dashboard -> NICAI
"""
from .vessel_intelligence_engine import (
    process_intelligence,
    determine_risk_level,
    determine_validation_status,
)

__all__ = [
    "process_intelligence",
    "determine_risk_level",
    "determine_validation_status",
]