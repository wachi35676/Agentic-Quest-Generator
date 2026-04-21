"""Prompt templates for the Critic quest generation pattern.

Two personas:
1. Generator — produces quest components (same prompts as ReAct/ToT)
2. Critic — evaluates each component against an explicit checklist

The Critic is GRANULAR: it reviews each component individually with an
adversarial checklist, unlike Reflection which reviews the whole quest.
"""

from config import CONFIG

GENERATOR_SYSTEM_PROMPT = """You are a video game quest designer. You create rich, detailed quests for a top-down adventure game.

IMPORTANT RULES:
- You MUST respond with ONLY a valid JSON object. No extra text before or after.
- Follow the exact JSON schema provided in each step.
- All locations MUST be from this list: {zones}
- Keep content appropriate for a fantasy adventure game.
- Be creative but consistent — each component should fit the quest's theme and storyline.
""".format(zones=", ".join(CONFIG.world_zones))


CRITIC_SYSTEM_PROMPT = """You are a strict quest quality reviewer. You evaluate quest components against an explicit checklist.

IMPORTANT RULES:
- You MUST respond with ONLY a valid JSON object.
- Be thorough and honest — flag every issue you find.
- For each checklist item, mark it as "pass" or "fail" with a specific reason.
- If ANY item fails, set "approved" to false and provide concrete revision instructions.
"""


# ---------------------------------------------------------------------------
# Component order (same as ReAct/ToT)
# ---------------------------------------------------------------------------
COMPONENT_ORDER = [
    "storyline",
    "objectives",
    "enemies",
    "subquests",
    "dialogs",
    "rewards",
    "puzzles",
    "lore_and_events",
]


# ---------------------------------------------------------------------------
# Generator prompts — same structure as ReAct
# ---------------------------------------------------------------------------

STORYLINE_PROMPT = """Generate a quest storyline based on this task:

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
REQUIRED ELEMENTS: {required_elements}

Respond with ONLY this JSON:
{{
    "title": "Quest Title",
    "description": "2-3 sentence quest summary",
    "storyline": [
        "Act 1: ...",
        "Act 2: ...",
        "Act 3: ..."
    ]
}}"""


OBJECTIVES_PROMPT = """Given this quest storyline, generate the main objectives.

QUEST TITLE: {title}
STORYLINE: {storyline}
DIFFICULTY: {difficulty}
CONSTRAINTS: {constraints}

Valid objective types: collect, kill, deliver, explore, escort, interact
Valid locations: {zones}

Respond with ONLY this JSON:
{{
    "objectives": [
        {{
            "id": "obj_001",
            "description": "What the player must do",
            "objective_type": "collect|kill|deliver|explore|escort|interact",
            "target": "what to collect/kill/find",
            "target_count": 1,
            "location": "location_from_valid_list",
            "is_optional": false,
            "prerequisites": []
        }}
    ]
}}

Include 3-5 objectives that follow the storyline progression. At least one should have a prerequisite."""


ENEMIES_PROMPT = """Given this quest, generate enemy encounters.

QUEST TITLE: {title}
STORYLINE: {storyline}
DIFFICULTY: {difficulty}
OBJECTIVES: {objectives}

Valid locations: {zones}
Narrative roles: guardian (guards an area/item), roaming (patrols), ambush (surprise attack), boss (main enemy)

Difficulty guide:
- easy: enemies HP 20-50, damage 3-8
- medium: enemies HP 40-100, damage 5-15
- hard: enemies HP 80-200, damage 10-25
- bosses: 2-3x normal stats

Respond with ONLY this JSON:
{{
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
    ]
}}

Include {max_enemies} or fewer enemies. At least one boss if required."""


SUBQUESTS_PROMPT = """Given this quest, generate sub-quests (side objectives).

QUEST TITLE: {title}
QUEST ID: {quest_id}
STORYLINE: {storyline}
MAIN OBJECTIVES: {objectives}

Valid sub-quest types: fetch, collect, deliver, escort, puzzle
Valid locations: {zones}

Respond with ONLY this JSON:
{{
    "sub_quests": [
        {{
            "id": "sq_001",
            "title": "Sub-quest Title",
            "description": "What this sub-quest is about",
            "quest_type": "fetch|collect|deliver|escort|puzzle",
            "parent_quest_id": "{quest_id}",
            "trigger_condition": "When this becomes available",
            "objectives": [
                {{
                    "id": "sq_obj_001",
                    "description": "Sub-quest objective",
                    "objective_type": "collect",
                    "target": "item_name",
                    "target_count": 1,
                    "location": "village",
                    "is_optional": false,
                    "prerequisites": []
                }}
            ],
            "rewards": [
                {{
                    "item_name": "Reward Item",
                    "item_type": "consumable",
                    "quantity": 1,
                    "stats": null
                }}
            ]
        }}
    ]
}}

Generate at least {min_subquests} sub-quests that connect to the main storyline."""


DIALOGS_PROMPT = """Given this quest, generate NPC dialog trees.

QUEST TITLE: {title}
STORYLINE: {storyline}
OBJECTIVES: {objectives}

Valid locations: {zones}

Respond with ONLY this JSON:
{{
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
                    "text": "Greetings, traveler...",
                    "next_node": "explain_quest",
                    "choices": null
                }},
                {{
                    "node_id": "explain_quest",
                    "speaker": "Elder Moira",
                    "text": "Something dark stirs in the forest...",
                    "next_node": null,
                    "choices": [
                        {{
                            "text": "I'll investigate right away.",
                            "next_node": "accept",
                            "consequence": null
                        }},
                        {{
                            "text": "What's in it for me?",
                            "next_node": "reward_talk",
                            "consequence": null
                        }}
                    ]
                }},
                {{
                    "node_id": "accept",
                    "speaker": "Elder Moira",
                    "text": "Thank you, brave one. Here, take this map.",
                    "next_node": null,
                    "choices": null
                }},
                {{
                    "node_id": "reward_talk",
                    "speaker": "Elder Moira",
                    "text": "The village treasury will reward you handsomely.",
                    "next_node": "accept",
                    "choices": null
                }}
            ]
        }}
    ]
}}

Generate 2-3 NPCs with dialog trees. Each tree should have 3-6 nodes with at least one choice point."""


REWARDS_PROMPT = """Given this quest, generate the rewards.

QUEST TITLE: {title}
DIFFICULTY: {difficulty}
OBJECTIVES: {objectives}
ENEMIES: {enemies}

Valid item types: weapon, armor, consumable, key_item, currency

Difficulty guide for rewards:
- easy: basic items, small gold amounts
- medium: good weapons/armor, moderate gold
- hard: powerful items, large gold, unique items

Respond with ONLY this JSON:
{{
    "rewards": [
        {{
            "item_name": "Forest Guardian's Blade",
            "item_type": "weapon",
            "quantity": 1,
            "stats": {{"damage": 12}}
        }},
        {{
            "item_name": "Gold Coins",
            "item_type": "currency",
            "quantity": 100,
            "stats": null
        }}
    ]
}}

Generate 3-5 rewards appropriate to the quest difficulty."""


PUZZLES_PROMPT = """Given this quest, generate environmental puzzles.

QUEST TITLE: {title}
STORYLINE: {storyline}
THEME: {theme}

Valid locations: {zones}

Respond with ONLY this JSON:
{{
    "puzzles": [
        {{
            "id": "puzzle_001",
            "description": "A stone door with three rune slots",
            "location": "ancient_ruins",
            "solution_hint": "The runes are scattered nearby on ancient pillars",
            "required_items": ["fire_rune", "water_rune", "earth_rune"],
            "reward": {{
                "item_name": "Ancient Amulet",
                "item_type": "key_item",
                "quantity": 1,
                "stats": null
            }},
            "unlocks": "hidden_chamber"
        }}
    ]
}}

Generate 1-2 puzzles that fit the quest theme."""


LORE_AND_EVENTS_PROMPT = """Given this quest, generate lore items, dynamic events, and branching consequences.

QUEST TITLE: {title}
QUEST ID: {quest_id}
STORYLINE: {storyline}
THEME: {theme}

Valid locations: {zones}

Respond with ONLY this JSON:
{{
    "lore_items": [
        {{
            "id": "lore_001",
            "title": "Ancient Scroll Fragment",
            "content": "The text tells of a time when the forest spirits...",
            "location": "dark_forest",
            "related_quest_id": "{quest_id}"
        }}
    ],
    "dynamic_events": [
        {{
            "id": "event_001",
            "trigger": "player_enters_dark_forest",
            "description": "An eerie mist rolls in as the player enters",
            "effects": ["reduce_visibility", "spawn_ambient_sounds"],
            "narrative_text": "A cold mist wraps around you as you step beneath the ancient canopy..."
        }}
    ],
    "branching_consequences": [
        {{
            "id": "branch_001",
            "trigger_choice": "spare_the_bandit_leader",
            "description": "Sparing the leader earns respect but some villagers distrust you",
            "world_changes": ["bandit_camp_becomes_trading_post"],
            "reputation_effect": 1,
            "unlocks_quest": "sq_reformed_bandits",
            "blocks_quest": null
        }}
    ]
}}

Generate 2-3 lore items, 1-2 dynamic events, and 1-2 branching consequences."""


# Map component names to generator prompts
COMPONENT_PROMPTS = {
    "storyline": STORYLINE_PROMPT,
    "objectives": OBJECTIVES_PROMPT,
    "enemies": ENEMIES_PROMPT,
    "subquests": SUBQUESTS_PROMPT,
    "dialogs": DIALOGS_PROMPT,
    "rewards": REWARDS_PROMPT,
    "puzzles": PUZZLES_PROMPT,
    "lore_and_events": LORE_AND_EVENTS_PROMPT,
}


# ---------------------------------------------------------------------------
# Revision prompts — used when critic finds issues
# ---------------------------------------------------------------------------

REVISION_PROMPT = """Revise this {component} based on the critic's feedback.

QUEST TITLE: {title}
THEME: {theme}
DIFFICULTY: {difficulty}

ORIGINAL {component_upper}:
{original_json}

CRITIC FEEDBACK:
{critic_feedback}

ISSUES TO FIX:
{issues_list}

Fix ALL the issues listed above. Keep what was good and only change what the critic flagged.
Respond with ONLY the corrected JSON in the same format as the original."""


# ---------------------------------------------------------------------------
# Critic prompts — one per component, with explicit checklists
# ---------------------------------------------------------------------------

STORYLINE_CRITIC_PROMPT = """Review this quest storyline against the checklist below.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
REQUIRED ELEMENTS: {required_elements}

STORYLINE TO REVIEW:
Title: {candidate_title}
Description: {candidate_description}
Storyline: {candidate_storyline}

CHECKLIST — evaluate each item as "pass" or "fail":
1. THEMATIC CONSISTENCY: Does the title and storyline match the theme "{theme}"?
2. NARRATIVE STRUCTURE: Does the storyline have a clear beginning, conflict, and resolution (at least 3 acts)?
3. DESCRIPTION QUALITY: Is the description 2-3 sentences that accurately summarize the quest?
4. REQUIRED ELEMENTS: Does the storyline incorporate the required elements ({required_elements})?
5. COMPLETENESS: Are all required fields present (title, description, storyline array)?

Respond with ONLY this JSON:
{{
    "checklist": [
        {{"item": "thematic_consistency", "result": "pass|fail", "reason": "why"}},
        {{"item": "narrative_structure", "result": "pass|fail", "reason": "why"}},
        {{"item": "description_quality", "result": "pass|fail", "reason": "why"}},
        {{"item": "required_elements", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness", "result": "pass|fail", "reason": "why"}}
    ],
    "approved": true,
    "issues": ["List of specific issues to fix, empty if approved"],
    "revision_instructions": "Specific instructions for the generator to fix issues, empty if approved"
}}"""


OBJECTIVES_CRITIC_PROMPT = """Review these quest objectives against the checklist below.

QUEST TITLE: {title}
STORYLINE: {storyline}
DIFFICULTY: {difficulty}
CONSTRAINTS: {constraints}

OBJECTIVES TO REVIEW:
{candidate_json}

CHECKLIST — evaluate each item as "pass" or "fail":
1. THEMATIC CONSISTENCY: Do objectives fit the quest storyline and theme?
2. DIFFICULTY BALANCE: Is the number and complexity of objectives appropriate for "{difficulty}" difficulty?
3. NARRATIVE COHERENCE: Do objectives follow a logical progression from the storyline?
4. COMPLETENESS: Are there at least 3 objectives with all required fields (id, description, objective_type, target, location)?
5. VALID LOCATIONS: Are all locations from the valid list ({zones})?
6. PREREQUISITES: Does at least one objective have a prerequisite that references another objective's id?

Respond with ONLY this JSON:
{{
    "checklist": [
        {{"item": "thematic_consistency", "result": "pass|fail", "reason": "why"}},
        {{"item": "difficulty_balance", "result": "pass|fail", "reason": "why"}},
        {{"item": "narrative_coherence", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness", "result": "pass|fail", "reason": "why"}},
        {{"item": "valid_locations", "result": "pass|fail", "reason": "why"}},
        {{"item": "prerequisites", "result": "pass|fail", "reason": "why"}}
    ],
    "approved": true,
    "issues": [],
    "revision_instructions": ""
}}"""


ENEMIES_CRITIC_PROMPT = """Review these enemy encounters against the checklist below.

QUEST TITLE: {title}
DIFFICULTY: {difficulty}
OBJECTIVES: {objectives}

ENEMIES TO REVIEW:
{candidate_json}

Difficulty stat ranges:
- easy: HP 20-50, damage 3-8
- medium: HP 40-100, damage 5-15
- hard: HP 80-200, damage 10-25
- bosses: 2-3x normal stats for the difficulty

CHECKLIST — evaluate each item as "pass" or "fail":
1. THEMATIC CONSISTENCY: Do enemy types fit the quest theme?
2. DIFFICULTY BALANCE: Are HP and damage values within the correct ranges for "{difficulty}" difficulty?
3. NARRATIVE COHERENCE: Do enemies appear in locations that match the objectives?
4. COMPLETENESS: Does each enemy have all required fields (id, enemy_type, display_name, hp, damage, location)?
5. BOSS PRESENCE: Is there at least one boss enemy (is_boss=true)?
6. VALID LOCATIONS: Are all enemy locations from the valid zones list ({zones})?

Respond with ONLY this JSON:
{{
    "checklist": [
        {{"item": "thematic_consistency", "result": "pass|fail", "reason": "why"}},
        {{"item": "difficulty_balance", "result": "pass|fail", "reason": "why"}},
        {{"item": "narrative_coherence", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness", "result": "pass|fail", "reason": "why"}},
        {{"item": "boss_presence", "result": "pass|fail", "reason": "why"}},
        {{"item": "valid_locations", "result": "pass|fail", "reason": "why"}}
    ],
    "approved": true,
    "issues": [],
    "revision_instructions": ""
}}"""


SUBQUESTS_CRITIC_PROMPT = """Review these sub-quests against the checklist below.

QUEST TITLE: {title}
STORYLINE: {storyline}
MAIN OBJECTIVES: {objectives}

SUB-QUESTS TO REVIEW:
{candidate_json}

CHECKLIST — evaluate each item as "pass" or "fail":
1. THEMATIC CONSISTENCY: Do sub-quests relate to the main quest theme and storyline?
2. DIFFICULTY BALANCE: Are sub-quest objectives reasonable in scope (not harder than main quest)?
3. NARRATIVE COHERENCE: Do sub-quests reference or connect to main quest characters/locations?
4. COMPLETENESS: Does each sub-quest have id, title, description, quest_type, at least one objective, and rewards?
5. VALID LOCATIONS: Are all locations from the valid zones list ({zones})?

Respond with ONLY this JSON:
{{
    "checklist": [
        {{"item": "thematic_consistency", "result": "pass|fail", "reason": "why"}},
        {{"item": "difficulty_balance", "result": "pass|fail", "reason": "why"}},
        {{"item": "narrative_coherence", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness", "result": "pass|fail", "reason": "why"}},
        {{"item": "valid_locations", "result": "pass|fail", "reason": "why"}}
    ],
    "approved": true,
    "issues": [],
    "revision_instructions": ""
}}"""


DIALOGS_CRITIC_PROMPT = """Review these NPC dialog trees against the checklist below.

QUEST TITLE: {title}
STORYLINE: {storyline}
OBJECTIVES: {objectives}

DIALOGS TO REVIEW:
{candidate_json}

CHECKLIST — evaluate each item as "pass" or "fail":
1. THEMATIC CONSISTENCY: Do NPC names, dialog text, and locations fit the quest theme?
2. DIFFICULTY BALANCE: Is dialog complexity appropriate (not too short, not overwhelming)?
3. NARRATIVE COHERENCE: Does dialog reference quest objectives, storyline events, or other NPCs?
4. COMPLETENESS: Does each NPC have npc_id, npc_name, location, entry_node, and a dialog_tree with at least 3 nodes?
5. DIALOG INTEGRITY: Do all next_node references point to valid node_ids within the same tree?
6. PLAYER CHOICE: Does at least one dialog tree include player choices?

Respond with ONLY this JSON:
{{
    "checklist": [
        {{"item": "thematic_consistency", "result": "pass|fail", "reason": "why"}},
        {{"item": "difficulty_balance", "result": "pass|fail", "reason": "why"}},
        {{"item": "narrative_coherence", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness", "result": "pass|fail", "reason": "why"}},
        {{"item": "dialog_integrity", "result": "pass|fail", "reason": "why"}},
        {{"item": "player_choice", "result": "pass|fail", "reason": "why"}}
    ],
    "approved": true,
    "issues": [],
    "revision_instructions": ""
}}"""


REWARDS_CRITIC_PROMPT = """Review these quest rewards against the checklist below.

QUEST TITLE: {title}
DIFFICULTY: {difficulty}
ENEMIES: {enemies}

REWARDS TO REVIEW:
{candidate_json}

CHECKLIST — evaluate each item as "pass" or "fail":
1. THEMATIC CONSISTENCY: Do reward names fit the quest theme (not generic)?
2. DIFFICULTY BALANCE: Are reward values appropriate for "{difficulty}" (easy=basic, medium=good, hard=powerful)?
3. COMPLETENESS: Are there 3-5 rewards, each with item_name, item_type, and quantity?
4. VARIETY: Are there at least 2 different item_types among the rewards?
5. STAT VALIDITY: Do weapons/armor rewards include a stats dict with reasonable values?

Respond with ONLY this JSON:
{{
    "checklist": [
        {{"item": "thematic_consistency", "result": "pass|fail", "reason": "why"}},
        {{"item": "difficulty_balance", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness", "result": "pass|fail", "reason": "why"}},
        {{"item": "variety", "result": "pass|fail", "reason": "why"}},
        {{"item": "stat_validity", "result": "pass|fail", "reason": "why"}}
    ],
    "approved": true,
    "issues": [],
    "revision_instructions": ""
}}"""


PUZZLES_CRITIC_PROMPT = """Review these environmental puzzles against the checklist below.

QUEST TITLE: {title}
THEME: {theme}
STORYLINE: {storyline}

PUZZLES TO REVIEW:
{candidate_json}

CHECKLIST — evaluate each item as "pass" or "fail":
1. THEMATIC CONSISTENCY: Do puzzles fit the quest theme "{theme}"?
2. DIFFICULTY BALANCE: Are puzzles solvable with available items/knowledge (not impossibly obscure)?
3. NARRATIVE COHERENCE: Do puzzles connect to the quest storyline or setting?
4. COMPLETENESS: Does each puzzle have id, description, location, solution_hint, required_items, and a reward?
5. VALID LOCATIONS: Are puzzle locations from the valid zones list ({zones})?

Respond with ONLY this JSON:
{{
    "checklist": [
        {{"item": "thematic_consistency", "result": "pass|fail", "reason": "why"}},
        {{"item": "difficulty_balance", "result": "pass|fail", "reason": "why"}},
        {{"item": "narrative_coherence", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness", "result": "pass|fail", "reason": "why"}},
        {{"item": "valid_locations", "result": "pass|fail", "reason": "why"}}
    ],
    "approved": true,
    "issues": [],
    "revision_instructions": ""
}}"""


LORE_AND_EVENTS_CRITIC_PROMPT = """Review these lore items, dynamic events, and branching consequences against the checklist below.

QUEST TITLE: {title}
THEME: {theme}
STORYLINE: {storyline}

CONTENT TO REVIEW:
{candidate_json}

CHECKLIST — evaluate each item as "pass" or "fail":
1. THEMATIC CONSISTENCY: Do lore items, events, and consequences relate to the quest theme "{theme}"?
2. NARRATIVE COHERENCE: Do these elements reference quest characters, locations, or events from the storyline?
3. COMPLETENESS (LORE): Are there at least 2 lore items with id, title, content, and location?
4. COMPLETENESS (EVENTS): Is there at least 1 dynamic event with id, trigger, description, and effects?
5. COMPLETENESS (BRANCHES): Is there at least 1 branching consequence with id, trigger_choice, description, and world_changes?
6. VALID LOCATIONS: Are all locations from the valid zones list ({zones})?

Respond with ONLY this JSON:
{{
    "checklist": [
        {{"item": "thematic_consistency", "result": "pass|fail", "reason": "why"}},
        {{"item": "narrative_coherence", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness_lore", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness_events", "result": "pass|fail", "reason": "why"}},
        {{"item": "completeness_branches", "result": "pass|fail", "reason": "why"}},
        {{"item": "valid_locations", "result": "pass|fail", "reason": "why"}}
    ],
    "approved": true,
    "issues": [],
    "revision_instructions": ""
}}"""


# Map component names to critic prompts
CRITIC_PROMPTS = {
    "storyline": STORYLINE_CRITIC_PROMPT,
    "objectives": OBJECTIVES_CRITIC_PROMPT,
    "enemies": ENEMIES_CRITIC_PROMPT,
    "subquests": SUBQUESTS_CRITIC_PROMPT,
    "dialogs": DIALOGS_CRITIC_PROMPT,
    "rewards": REWARDS_CRITIC_PROMPT,
    "puzzles": PUZZLES_CRITIC_PROMPT,
    "lore_and_events": LORE_AND_EVENTS_CRITIC_PROMPT,
}
