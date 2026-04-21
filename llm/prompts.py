"""Shared prompt utilities for all agentic patterns."""

from config import CONFIG


def get_zone_list() -> str:
    """Get a formatted list of valid world zones."""
    return ", ".join(CONFIG.world_zones)


def inject_schema_hint(prompt: str, schema_example: dict) -> str:
    """Inject a JSON schema example into a prompt."""
    import json
    schema_str = json.dumps(schema_example, indent=2)
    return f"{prompt}\n\nExpected JSON format:\n```json\n{schema_str}\n```"


def build_context_summary(scratchpad: dict) -> str:
    """Build a text summary of what's been generated so far."""
    parts = []
    if scratchpad.get("title"):
        parts.append(f"Quest Title: {scratchpad['title']}")
    if scratchpad.get("storyline"):
        parts.append(f"Storyline: {' -> '.join(scratchpad['storyline'])}")
    if scratchpad.get("objectives"):
        parts.append(f"Objectives: {len(scratchpad['objectives'])} defined")
    if scratchpad.get("enemies"):
        parts.append(f"Enemies: {len(scratchpad['enemies'])} defined")
    if scratchpad.get("sub_quests"):
        parts.append(f"Sub-quests: {len(scratchpad['sub_quests'])} defined")
    if scratchpad.get("npc_dialogs"):
        parts.append(f"NPC Dialogs: {len(scratchpad['npc_dialogs'])} defined")
    return "\n".join(parts) if parts else "Nothing generated yet."
