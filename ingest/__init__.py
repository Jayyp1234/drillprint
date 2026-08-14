"""Ingestion layer: channel registry + per-session ring buffers (A15)."""

from .channels import REGISTRY, observability_badges
from .sessions import Session

__all__ = ["REGISTRY", "Session", "observability_badges"]
