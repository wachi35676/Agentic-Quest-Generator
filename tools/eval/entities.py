"""Loads the entities.json snapshot the Godot game writes at session start.

Used by metrics.py to cross-check that LLM-emitted entity references are
real (NPC names, item ids, character sheets, position hints, action verbs).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_entities(path: str | Path) -> dict[str, set[str]]:
    """Returns a dict of name -> set(strings) for fast membership tests.

    Keys: item_ids, character_sheets, position_hints, objective_types,
    action_prefixes, action_bare, hand_placed_npcs.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"entities.json not found at {p}")
    raw: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return {k: set(v) for k, v in raw.items() if isinstance(v, list)}


def merge_entities(*sets: dict[str, set[str]]) -> dict[str, set[str]]:
    """Combine multiple entity snapshots (rarely needed, but useful when
    sessions came from different code revisions)."""
    merged: dict[str, set[str]] = {}
    for d in sets:
        for k, v in d.items():
            merged.setdefault(k, set()).update(v)
    return merged
