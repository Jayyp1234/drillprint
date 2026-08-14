"""Replay players for SIMULATE / demo (M4)."""

from .stream_player import (
    chunk_channel,
    ensure_rig_at,
    feed_episode,
    inject_rig_context,
    play,
)

__all__ = [
    "chunk_channel",
    "ensure_rig_at",
    "feed_episode",
    "inject_rig_context",
    "play",
]
