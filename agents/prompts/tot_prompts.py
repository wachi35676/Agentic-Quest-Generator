"""Prompt templates for the Tree of Thought quest generation pattern.

Each component has:
1. A generation prompt (produces a candidate)
2. A scoring prompt (evaluates the candidate on a concrete rubric, returns 0.0-1.0)

Scoring rubrics are deliberately concrete so the 8B model can follow them
without vague "rate quality" instructions.
"""

from config import CONFIG

SYSTEM_PROMPT = """You are a video game quest designer. You create rich, detailed quests for a top-down adventure game.

IMPORTANT RULES:
- You MUST respond with ONLY a valid JSON object. No extra text before or after.
- Follow the exact JSON schema provided in each step.
- All locations MUST be from this list: {zones}
- Keep content appropriate for a fantasy adventure game.
- Be creative but consistent — each component should fit the quest's theme and storyline.
""".format(zones=", ".join(CONFIG.world_zones))


SCORING_SYSTEM_PROMPT = """You are a quest quality evaluator. You score quest components on specific criteria.

IMPORTANT RULES:
- You MUST respond with ONLY a valid JSON object.
- Each criterion gets a specific score. Add them up for the total.
- Be strict — only award points when the criterion is clearly met.
- Respond with the exact JSON format requested.
"""


# ---------------------------------------------------------------------------
# Component order (same as ReAct)
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
# Generation prompts — one per component
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


# Map component names to generation prompts
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
# Scoring prompts — concrete rubrics for each component
# ---------------------------------------------------------------------------

STORYLINE_SCORING_PROMPT = """Score this quest storyline on the rubric below.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}

CANDIDATE STORYLINE:
Title: {candidate_title}
Description: {candidate_description}
Storyline beats: {candidate_storyline}

SCORING RUBRIC (add up the points):
1. Does the storyline have a clear beginning, conflict, and resolution? Award 0.3 if yes, 0.0 if no.
2. Does the title fit the theme "{theme}"? Award 0.2 if yes, 0.0 if no.
3. Is the description 2-3 sentences and summarizes the quest? Award 0.1 if yes, 0.0 if no.
4. Are there at least 3 storyline beats (acts)? Award 0.2 if yes, 0.0 if no.
5. Is the content creative and not generic? Award 0.2 if yes, 0.1 if somewhat.

Respond with ONLY this JSON:
{{
    "criterion_1": 0.0,
    "criterion_2": 0.0,
    "criterion_3": 0.0,
    "criterion_4": 0.0,
    "criterion_5": 0.0,
    "total_score": 0.0,
    "reasoning": "Brief explanation"
}}"""


OBJECTIVES_SCORING_PROMPT = """Score these quest objectives on the rubric below.

QUEST TITLE: {title}
STORYLINE: {storyline}
DIFFICULTY: {difficulty}

CANDIDATE OBJECTIVES:
{candidate_json}

SCORING RUBRIC (add up the points):
1. Are there at least 3 objectives? Award 0.2 if yes, 0.0 if no.
2. Do objectives follow the storyline progression logically? Award 0.2 if yes, 0.0 if no.
3. Do locations match valid world zones ({zones})? Award 0.2 if all valid, 0.1 if most valid, 0.0 if many invalid.
4. Is there at least one objective with a prerequisite? Award 0.2 if yes, 0.0 if no.
5. Are objective types varied (not all the same type)? Award 0.2 if yes, 0.1 if somewhat, 0.0 if no.

Respond with ONLY this JSON:
{{
    "criterion_1": 0.0,
    "criterion_2": 0.0,
    "criterion_3": 0.0,
    "criterion_4": 0.0,
    "criterion_5": 0.0,
    "total_score": 0.0,
    "reasoning": "Brief explanation"
}}"""


ENEMIES_SCORING_PROMPT = """Score these enemy encounters on the rubric below.

QUEST TITLE: {title}
DIFFICULTY: {difficulty}

CANDIDATE ENEMIES:
{candidate_json}

SCORING RUBRIC (add up the points):
1. Do HP values match the difficulty guide (easy: 20-50, medium: 40-100, hard: 80-200, bosses: 2-3x)? Award 0.25 if yes, 0.1 if close, 0.0 if way off.
2. Do damage values match the difficulty guide (easy: 3-8, medium: 5-15, hard: 10-25)? Award 0.25 if yes, 0.1 if close, 0.0 if way off.
3. Do locations match valid world zones ({zones})? Award 0.2 if all valid, 0.0 if not.
4. Is there at least one boss enemy? Award 0.15 if yes, 0.0 if no.
5. Do enemies have varied narrative roles (not all "roaming")? Award 0.15 if yes, 0.0 if no.

Respond with ONLY this JSON:
{{
    "criterion_1": 0.0,
    "criterion_2": 0.0,
    "criterion_3": 0.0,
    "criterion_4": 0.0,
    "criterion_5": 0.0,
    "total_score": 0.0,
    "reasoning": "Brief explanation"
}}"""


SUBQUESTS_SCORING_PROMPT = """Score these sub-quests on the rubric below.

QUEST TITLE: {title}
STORYLINE: {storyline}

CANDIDATE SUB-QUESTS:
{candidate_json}

SCORING RUBRIC (add up the points):
1. Is there at least {min_subquests} sub-quest? Award 0.2 if yes, 0.0 if no.
2. Do sub-quests connect to the main storyline thematically? Award 0.3 if yes, 0.1 if weakly, 0.0 if no.
3. Does each sub-quest have at least one objective? Award 0.2 if yes, 0.0 if no.
4. Does each sub-quest have rewards? Award 0.15 if yes, 0.0 if no.
5. Do locations match valid world zones ({zones})? Award 0.15 if yes, 0.0 if not.

Respond with ONLY this JSON:
{{
    "criterion_1": 0.0,
    "criterion_2": 0.0,
    "criterion_3": 0.0,
    "criterion_4": 0.0,
    "criterion_5": 0.0,
    "total_score": 0.0,
    "reasoning": "Brief explanation"
}}"""


DIALOGS_SCORING_PROMPT = """Score these NPC dialog trees on the rubric below.

QUEST TITLE: {title}
STORYLINE: {storyline}

CANDIDATE DIALOGS:
{candidate_json}

SCORING RUBRIC (add up the points):
1. Are there at least 2 NPCs with dialog? Award 0.2 if yes, 0.0 if no.
2. Does each dialog tree have 3-6 nodes? Award 0.2 if yes, 0.1 if close, 0.0 if no.
3. Does at least one dialog have player choices? Award 0.2 if yes, 0.0 if no.
4. Do dialog node_ids link correctly (next_node references exist)? Award 0.2 if yes, 0.0 if broken links.
5. Is the dialog text natural and fits the quest theme? Award 0.2 if yes, 0.1 if somewhat, 0.0 if no.

Respond with ONLY this JSON:
{{
    "criterion_1": 0.0,
    "criterion_2": 0.0,
    "criterion_3": 0.0,
    "criterion_4": 0.0,
    "criterion_5": 0.0,
    "total_score": 0.0,
    "reasoning": "Brief explanation"
}}"""


REWARDS_SCORING_PROMPT = """Score these quest rewards on the rubric below.

QUEST TITLE: {title}
DIFFICULTY: {difficulty}

CANDIDATE REWARDS:
{candidate_json}

SCORING RUBRIC (add up the points):
1. Are there 3-5 rewards? Award 0.2 if yes, 0.1 if 1-2, 0.0 if none.
2. Do reward values match the difficulty (easy=small, medium=moderate, hard=powerful)? Award 0.25 if yes, 0.0 if no.
3. Is there at least one weapon or armor reward? Award 0.2 if yes, 0.0 if no.
4. Is there a currency reward? Award 0.15 if yes, 0.0 if no.
5. Are item types varied (not all the same)? Award 0.2 if yes, 0.0 if no.

Respond with ONLY this JSON:
{{
    "criterion_1": 0.0,
    "criterion_2": 0.0,
    "criterion_3": 0.0,
    "criterion_4": 0.0,
    "criterion_5": 0.0,
    "total_score": 0.0,
    "reasoning": "Brief explanation"
}}"""


PUZZLES_SCORING_PROMPT = """Score these environmental puzzles on the rubric below.

QUEST TITLE: {title}
THEME: {theme}

CANDIDATE PUZZLES:
{candidate_json}

SCORING RUBRIC (add up the points):
1. Is there at least 1 puzzle? Award 0.2 if yes, 0.0 if no.
2. Does the puzzle fit the quest theme "{theme}"? Award 0.3 if yes, 0.1 if weakly, 0.0 if no.
3. Does the puzzle have required_items and a solution_hint? Award 0.2 if yes, 0.0 if missing.
4. Does the puzzle have a reward? Award 0.15 if yes, 0.0 if no.
5. Does the location match a valid world zone ({zones})? Award 0.15 if yes, 0.0 if not.

Respond with ONLY this JSON:
{{
    "criterion_1": 0.0,
    "criterion_2": 0.0,
    "criterion_3": 0.0,
    "criterion_4": 0.0,
    "criterion_5": 0.0,
    "total_score": 0.0,
    "reasoning": "Brief explanation"
}}"""


LORE_AND_EVENTS_SCORING_PROMPT = """Score these lore items, events, and branching consequences on the rubric below.

QUEST TITLE: {title}
THEME: {theme}

CANDIDATE CONTENT:
{candidate_json}

SCORING RUBRIC (add up the points):
1. Are there at least 2 lore items? Award 0.15 if yes, 0.0 if no.
2. Is there at least 1 dynamic event? Award 0.15 if yes, 0.0 if no.
3. Is there at least 1 branching consequence? Award 0.15 if yes, 0.0 if no.
4. Do lore items relate to the quest theme "{theme}"? Award 0.2 if yes, 0.0 if no.
5. Do events have clear triggers and effects? Award 0.15 if yes, 0.0 if no.
6. Do branching consequences have world_changes and reputation_effect? Award 0.2 if yes, 0.0 if no.

Respond with ONLY this JSON:
{{
    "criterion_1": 0.0,
    "criterion_2": 0.0,
    "criterion_3": 0.0,
    "criterion_4": 0.0,
    "criterion_5": 0.0,
    "criterion_6": 0.0,
    "total_score": 0.0,
    "reasoning": "Brief explanation"
}}"""


# Map component names to scoring prompts
SCORING_PROMPTS = {
    "storyline": STORYLINE_SCORING_PROMPT,
    "objectives": OBJECTIVES_SCORING_PROMPT,
    "enemies": ENEMIES_SCORING_PROMPT,
    "subquests": SUBQUESTS_SCORING_PROMPT,
    "dialogs": DIALOGS_SCORING_PROMPT,
    "rewards": REWARDS_SCORING_PROMPT,
    "puzzles": PUZZLES_SCORING_PROMPT,
    "lore_and_events": LORE_AND_EVENTS_SCORING_PROMPT,
}
