"""The five paper metrics, computed from a session's event stream.

Each function takes a list of dicts (one per event), returns a dict of
result fields. Pure functions; safe to call with any subset of events.
"""
from __future__ import annotations

from statistics import mean, median
from typing import Any


# --------------------------------------------------------------------------
# Metric 1: Structural Adherence
# Pct of `quest_generated` events whose schema validation passed.
# --------------------------------------------------------------------------

def structural_adherence(events: list[dict]) -> dict[str, Any]:
    quests = [e for e in events if e["event_type"] == "quest_generated"]
    if not quests:
        return {"n": 0, "pass_rate": None, "parse_rate": None}
    parsed = [q for q in quests if q["payload"].get("parsed_ok")]
    valid = [q for q in parsed if q["payload"].get("schema_valid")]
    return {
        "n": len(quests),
        "parse_rate": len(parsed) / len(quests),
        "pass_rate": len(valid) / len(quests),
        "avg_attempts": mean(q["payload"].get("attempt", 1) for q in quests),
        "avg_sanitizer_fixes": mean(
            q["payload"].get("sanitizer_fix_count", 0) for q in quests
        ),
    }


# --------------------------------------------------------------------------
# Metric 2: Accuracy of Given Strings
# Pct of entity references in quest_generated payloads that exist in
# the authoritative entity catalog.
#
# Looks at: npc_count metadata isn't enough; we need the bundle. We log
# `quest_id`, `npc_count`, `branch_count` but not the full bundle. So this
# metric runs over `world_npcs` (session_start) + npc references derived
# from `player_action` events whose target NPC must exist.
#
# Better: when payload has `raw_text`, parse it and walk references. The
# Godot side currently doesn't ship raw_text in the structured event for
# size reasons — but we DO log raw_text_len. For full string-accuracy we
# rely on the validation_errors list: if the validator rejected the bundle
# for "unknown npc 'X'" we already know it failed. For the kept bundle,
# all references are by construction valid.
#
# This implementation: count successful bundles → 1.0 (all valid by
# validation). Each failed bundle contributes 0. Partial breakdown by
# error category (npc / item / sheet) extracted from validation_errors.
# --------------------------------------------------------------------------

_ERROR_CATEGORIES = (
    ("npc",   ("references unknown npc", "an npc is missing 'npc_name'", "duplicate npc_name")),
    ("item",  ("not in catalog", "params.item_id", "reward.item_id")),
    ("sheet", ("character_sheet",)),
    ("hint",  ("position_hint",)),
)


def _categorise(err: str) -> str:
    el = err.lower()
    for cat, needles in _ERROR_CATEGORIES:
        if any(n in el for n in needles):
            return cat
    return "other"


def string_accuracy(events: list[dict], entities: dict[str, set[str]]) -> dict[str, Any]:
    quests = [e for e in events if e["event_type"] == "quest_generated"]
    if not quests:
        return {"n": 0, "accuracy": None}
    by_cat: dict[str, list[int]] = {"npc": [], "item": [], "sheet": [], "hint": [], "other": []}
    successes = 0
    for q in quests:
        payload = q["payload"]
        if payload.get("schema_valid"):
            successes += 1
        # Also tally categorised validation errors when the bundle failed.
        for err in payload.get("validation_errors", []) or []:
            by_cat[_categorise(err)].append(1)
    accuracy = successes / len(quests)
    return {
        "n": len(quests),
        "accuracy": accuracy,
        "errors_by_category": {k: len(v) for k, v in by_cat.items()},
    }


# --------------------------------------------------------------------------
# Metric 3: Adaptation Rate
# Continuation chapters per session, normalized by play time.
# --------------------------------------------------------------------------

def adaptation_rate(events: list[dict]) -> dict[str, Any]:
    revisions = [e for e in events if e["event_type"] == "quest_revised"]
    completions = [
        e for e in events
        if e["event_type"] == "orchestration_complete"
    ]
    duration_ms = _session_duration_ms(events)
    duration_min = duration_ms / 60_000.0 if duration_ms else 0.0
    return {
        "total_revisions": len(revisions),
        "completions": len(completions),
        "duration_min": duration_min,
        "revisions_per_hour": (len(revisions) / duration_min * 60.0) if duration_min > 0 else None,
    }


def _session_duration_ms(events: list[dict]) -> int:
    # Prefer the explicit session_end payload; fall back to last/first ts.
    starts = [e for e in events if e["event_type"] == "session_start"]
    ends = [e for e in events if e["event_type"] == "session_end"]
    if ends:
        return int(ends[-1]["payload"].get("duration_ms", 0))
    if not events:
        return 0
    return int(events[-1]["timestamp_ms"]) - int(events[0]["timestamp_ms"])


# --------------------------------------------------------------------------
# Metric 4: Memory Consistency
# Pct of memory_claim events with verified=True.
# --------------------------------------------------------------------------

def memory_consistency(events: list[dict]) -> dict[str, Any]:
    claims = [e for e in events if e["event_type"] == "memory_claim"]
    if not claims:
        return {"n": 0, "consistency": None}
    verified = sum(1 for c in claims if c["payload"].get("verified"))
    return {
        "n": len(claims),
        "consistency": verified / len(claims),
        "verified": verified,
        "total": len(claims),
    }


# --------------------------------------------------------------------------
# Metric 5: Replanning Latency
# Time between replan_triggered and replan_completed for the same prev_quest_id.
# --------------------------------------------------------------------------

def replanning_latency(events: list[dict]) -> dict[str, Any]:
    triggers = {}
    completions = []
    for e in events:
        et = e["event_type"]
        if et == "replan_triggered":
            triggers[e["payload"].get("prev_quest_id", "")] = e["timestamp_ms"]
        elif et == "replan_completed":
            qid = e["payload"].get("prev_quest_id", "")
            if qid in triggers:
                completions.append(e["timestamp_ms"] - triggers[qid])
    if not completions:
        return {"n": 0}
    s = sorted(completions)
    return {
        "n": len(s),
        "mean_ms": mean(s),
        "median_ms": median(s),
        "p95_ms": s[int(len(s) * 0.95)] if len(s) >= 20 else s[-1],
        "max_ms": max(s),
    }


# --------------------------------------------------------------------------
# All-in-one helper for runner.py
# --------------------------------------------------------------------------

def all_metrics(events: list[dict], entities: dict[str, set[str]]) -> dict[str, Any]:
    return {
        "structural": structural_adherence(events),
        "strings": string_accuracy(events, entities),
        "adaptation": adaptation_rate(events),
        "memory": memory_consistency(events),
        "latency": replanning_latency(events),
    }
