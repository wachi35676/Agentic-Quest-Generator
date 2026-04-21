"""Prompt templates for the Reflection quest generation pattern.

The Reflection pattern is HOLISTIC: it generates the entire quest in one shot,
then reflects on the whole thing, then revises the whole thing. This contrasts
with the Critic pattern which reviews each component individually.

Three phases:
  1. DRAFT  — Generate the complete quest as a single JSON object.
  2. REFLECT — Given the full quest JSON, produce a structured critique.
  3. REVISE  — Given both quest JSON and critique, produce an improved quest.

Phases 2-3 repeat for K rounds (CONFIG.reflection_max_rounds).
"""

from config import CONFIG

_ZONES = ", ".join(CONFIG.world_zones)

# ---------------------------------------------------------------------------
# System prompt — shared across all three phases
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are an expert video game quest designer for a top-down fantasy adventure game. "
    "You always respond with ONLY valid JSON — no explanation, no markdown headings, "
    "no text before or after the JSON object. "
    "All locations MUST be chosen from this list: " + _ZONES + ". "
    "Be creative, but keep every field consistent with the quest's theme and difficulty."
)

# ---------------------------------------------------------------------------
# Phase 1: DRAFT — generate the entire quest in one shot
# ---------------------------------------------------------------------------
DRAFT_PROMPT = """Generate a COMPLETE quest as a single JSON object.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
REQUIRED ELEMENTS: {required_elements}
CONSTRAINTS: {constraints}

Valid locations: {zones}
Valid objective types: collect, kill, deliver, explore, escort, interact
Valid enemy narrative roles: guardian, roaming, ambush, boss
Valid item types: weapon, armor, consumable, key_item, currency
Valid sub-quest types: fetch, collect, deliver, escort, puzzle

Difficulty guide for enemy stats:
- easy:   HP 20-50,  damage 3-8
- medium: HP 40-100, damage 5-15
- hard:   HP 80-200, damage 10-25
- bosses: 2-3x the normal range

Respond with ONLY this JSON (fill in ALL fields):
{{
    "title": "Quest Title Here",
    "description": "2-3 sentence quest summary",
    "storyline": [
        "Act 1: Opening — describe the inciting incident",
        "Act 2: Rising action — describe the main challenge",
        "Act 3: Climax and resolution — describe the finale"
    ],
    "objectives": [
        {{
            "id": "obj_001",
            "description": "What the player must do",
            "objective_type": "collect",
            "target": "item_or_enemy_name",
            "target_count": 1,
            "location": "village",
            "is_optional": false,
            "completed": false,
            "prerequisites": []
        }}
    ],
    "enemies": [
        {{
            "id": "enemy_001",
            "enemy_type": "spider",
            "display_name": "Forest Spider",
            "hp": 40,
            "damage": 8,
            "location": "dark_forest",
            "count": 3,
            "is_boss": false,
            "loot_table": ["spider_silk"],
            "narrative_role": "roaming"
        }}
    ],
    "sub_quests": [
        {{
            "id": "sq_001",
            "title": "Side Quest Title",
            "description": "What this side quest is about",
            "quest_type": "fetch",
            "parent_quest_id": "{quest_id}",
            "trigger_condition": "After completing obj_001",
            "objectives": [
                {{
                    "id": "sq_obj_001",
                    "description": "Sub-quest objective description",
                    "objective_type": "collect",
                    "target": "herb",
                    "target_count": 3,
                    "location": "dark_forest",
                    "is_optional": false,
                    "completed": false,
                    "prerequisites": []
                }}
            ],
            "rewards": [
                {{
                    "item_name": "Healing Potion",
                    "item_type": "consumable",
                    "quantity": 2,
                    "stats": null
                }}
            ],
            "dialogs": []
        }}
    ],
    "npc_dialogs": [
        {{
            "npc_id": "npc_001",
            "npc_name": "Elder Moira",
            "location": "village",
            "entry_node": "greeting",
            "dialog_tree": [
                {{
                    "node_id": "greeting",
                    "speaker": "Elder Moira",
                    "text": "Greetings, traveler. Dark times have befallen our village...",
                    "next_node": "explain",
                    "choices": null
                }},
                {{
                    "node_id": "explain",
                    "speaker": "Elder Moira",
                    "text": "Will you help us?",
                    "next_node": null,
                    "choices": [
                        {{
                            "text": "I will help.",
                            "next_node": "accept",
                            "consequence": null
                        }},
                        {{
                            "text": "What is the reward?",
                            "next_node": "reward_info",
                            "consequence": null
                        }}
                    ]
                }},
                {{
                    "node_id": "accept",
                    "speaker": "Elder Moira",
                    "text": "Thank you, brave soul.",
                    "next_node": null,
                    "choices": null
                }},
                {{
                    "node_id": "reward_info",
                    "speaker": "Elder Moira",
                    "text": "The village will reward you handsomely.",
                    "next_node": "accept",
                    "choices": null
                }}
            ]
        }}
    ],
    "rewards": [
        {{
            "item_name": "Gold Coins",
            "item_type": "currency",
            "quantity": 150,
            "stats": null
        }},
        {{
            "item_name": "Forest Guardian Blade",
            "item_type": "weapon",
            "quantity": 1,
            "stats": {{"damage": 12}}
        }}
    ],
    "puzzles": [
        {{
            "id": "puzzle_001",
            "description": "A locked stone door with three rune slots",
            "location": "ancient_ruins",
            "solution_hint": "Find the runes hidden on nearby pillars",
            "required_items": ["fire_rune", "water_rune", "earth_rune"],
            "reward": {{
                "item_name": "Ancient Amulet",
                "item_type": "key_item",
                "quantity": 1,
                "stats": null
            }},
            "unlocks": "hidden_chamber"
        }}
    ],
    "lore_items": [
        {{
            "id": "lore_001",
            "title": "Worn Journal Page",
            "content": "A faded entry describes the fall of an ancient order...",
            "location": "ancient_ruins",
            "related_quest_id": "{quest_id}"
        }}
    ],
    "dynamic_events": [
        {{
            "id": "event_001",
            "trigger": "player_enters_dark_forest",
            "description": "A cold mist rolls in as the player enters the forest",
            "effects": ["reduce_visibility", "spawn_ambient_sounds"],
            "narrative_text": "The canopy closes above you and an unnatural fog creeps along the ground..."
        }}
    ],
    "branching_consequences": [
        {{
            "id": "branch_001",
            "trigger_choice": "spare_the_bandit_leader",
            "description": "Sparing the leader changes the camp into a trading post",
            "world_changes": ["bandit_camp_becomes_trading_post"],
            "reputation_effect": 1,
            "unlocks_quest": null,
            "blocks_quest": null
        }}
    ]
}}

REQUIREMENTS:
- Include 3-5 main objectives with at least one prerequisite chain.
- Include 3-6 enemies with at least one boss encounter.
- Include at least 1 sub-quest.
- Include 2-3 NPCs with dialog trees (3-6 nodes each, at least one choice point).
- Include 3-5 rewards scaled to difficulty.
- Include 1-2 puzzles.
- Include 1-3 lore items, 1-2 dynamic events, and 1-2 branching consequences.
- Every location must be from the valid locations list.
- All IDs must be unique across the entire quest."""


# ---------------------------------------------------------------------------
# Phase 2: REFLECT — holistic critique of the complete quest
# ---------------------------------------------------------------------------
REFLECT_PROMPT = """You are reviewing a generated quest for quality. Analyze the ENTIRE quest below and identify weaknesses.

Here is the complete quest JSON:
```json
{quest_json}
```

Evaluate the quest on these dimensions and give a structured critique. Be specific — cite exact IDs, names, and fields. For each issue, explain WHY it is a problem and WHAT would fix it.

Respond with ONLY this JSON:
{{
    "overall_quality": "poor|fair|good|excellent",
    "issues": [
        {{
            "category": "plot_hole|balance|dialog|consistency|missing_content|bland_content|broken_reference",
            "severity": "minor|moderate|critical",
            "description": "Specific description of the issue",
            "location": "Which part of the quest (e.g. objective obj_002, NPC npc_001, enemy enemy_003)",
            "suggestion": "Concrete fix suggestion"
        }}
    ],
    "strengths": [
        "What the quest does well (1-3 bullet points)"
    ],
    "missing_elements": [
        "Anything important that is absent (e.g. no boss fight, no choice consequences, objectives have no prerequisite chain)"
    ],
    "balance_assessment": {{
        "enemy_difficulty": "too_easy|appropriate|too_hard",
        "reward_value": "too_low|appropriate|too_high",
        "quest_length": "too_short|appropriate|too_long",
        "notes": "Brief balance notes"
    }}
}}

EXAMPLE critique issue:
{{
    "category": "plot_hole",
    "severity": "critical",
    "description": "Objective obj_003 asks the player to deliver the Sacred Gem to the Elder, but no earlier objective or enemy drop provides the Sacred Gem.",
    "location": "objective obj_003",
    "suggestion": "Add a collect objective before obj_003 or add Sacred Gem to a boss loot_table."
}}

Be thorough. Find at least 3 issues if they exist. Do not invent problems that are not there — if the quest is genuinely strong, say so and list fewer issues."""


# ---------------------------------------------------------------------------
# Phase 3: REVISE — improve the quest based on the critique
# ---------------------------------------------------------------------------
REVISE_PROMPT = """You previously generated a quest, and it was critiqued. Now produce an IMPROVED version that addresses the critique.

ORIGINAL QUEST JSON:
```json
{quest_json}
```

CRITIQUE:
```json
{critique_json}
```

RULES FOR THE REVISION:
1. Fix every "critical" severity issue from the critique.
2. Fix as many "moderate" issues as possible.
3. Consider "minor" issues but do not break other things to fix them.
4. Preserve the strengths identified in the critique.
5. Keep the same quest ID, theme, and difficulty.
6. All locations MUST be from: {zones}
7. All IDs must remain unique.
8. Do NOT remove content that was working well — only improve or replace weak parts.

Respond with ONLY the complete revised quest JSON in the exact same schema as the original. Do not include any text outside the JSON object.

The JSON schema is identical to the original quest (title, description, storyline, objectives, enemies, sub_quests, npc_dialogs, rewards, puzzles, lore_items, dynamic_events, branching_consequences)."""
