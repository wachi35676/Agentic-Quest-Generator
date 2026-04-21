"""Prompt templates for the Plan & Execute quest generation pattern.

The Plan & Execute pattern lets the LLM decide how to decompose the
quest generation task into steps, then executes each step sequentially
with full context of prior results.
"""

from config import CONFIG

SYSTEM_PROMPT = """You are a video game quest designer. You create rich, detailed quests for a top-down adventure game.

IMPORTANT RULES:
- You MUST respond with ONLY a valid JSON object. No extra text before or after.
- Do NOT include any explanation, commentary, or markdown formatting.
- Follow the exact JSON schema provided in each step.
- All locations MUST be from this list: {zones}
- Keep content appropriate for a fantasy adventure game.
- Be creative but consistent with the quest's theme and storyline.
""".format(zones=", ".join(CONFIG.world_zones))


PLAN_PROMPT = """You are planning how to build a video game quest. Break the task into a numbered plan.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
REQUIRED ELEMENTS: {required_elements}
CONSTRAINTS: {constraints}
VALID LOCATIONS: {zones}

Create a plan with exactly {max_steps} steps to build this quest. Each step should produce one part of the quest.

Your steps MUST cover these quest components (in any order you choose):
- Quest title, description, and storyline (narrative acts)
- Quest objectives (things the player must do)
- Enemy encounters (monsters/bosses to fight)
- Sub-quests (optional side objectives)
- NPC dialogs (conversation trees with choices)
- Rewards (items and currency the player earns)
- Environmental puzzles (puzzles in the game world)
- Lore items, dynamic events, and branching consequences

You MUST respond with ONLY this JSON object and nothing else:
{{
    "type": "plan",
    "steps": [
        "Step 1 description here",
        "Step 2 description here",
        "Step 3 description here",
        "Step 4 description here",
        "Step 5 description here",
        "Step 6 description here",
        "Step 7 description here",
        "Step 8 description here"
    ]
}}

The "steps" array must have exactly {max_steps} strings. Each string describes what that step will produce.
Respond with ONLY the JSON object above. No other text."""


REPLAN_PROMPT = """Your previous plan step failed to produce valid output. You need to create a new plan for the remaining work.

ORIGINAL TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}

COMPLETED STEPS AND THEIR RESULTS:
{completed_results}

FAILED STEP: Step {failed_step_number} - "{failed_step_description}"
FAILURE REASON: Could not parse valid JSON from the LLM response.

Create a new plan for the remaining {remaining_steps} steps to complete the quest. The new plan should cover any quest components not yet produced.

You MUST respond with ONLY this JSON object and nothing else:
{{
    "type": "plan",
    "steps": [
        "New step 1 description",
        "New step 2 description"
    ]
}}

The "steps" array should have {remaining_steps} strings covering the remaining work.
Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_STORYLINE = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
REQUIRED ELEMENTS: {required_elements}
VALID LOCATIONS: {zones}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

For this step, generate the quest title, description, and storyline.

You MUST respond with ONLY this JSON object and nothing else:
{{
    "component": "storyline",
    "title": "Quest Title Here",
    "description": "A 2-3 sentence quest summary describing what the player will do",
    "storyline": [
        "Act 1: Description of the first act",
        "Act 2: Description of the second act",
        "Act 3: Description of the third act"
    ]
}}

Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_OBJECTIVES = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
CONSTRAINTS: {constraints}
VALID LOCATIONS: {zones}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

For this step, generate 3-5 quest objectives. At least one objective should have a prerequisite (another objective that must be completed first).

Valid objective types: collect, kill, deliver, explore, escort, interact

You MUST respond with ONLY this JSON object and nothing else:
{{
    "component": "objectives",
    "objectives": [
        {{
            "id": "obj_001",
            "description": "What the player must do",
            "objective_type": "explore",
            "target": "what to find or do",
            "target_count": 1,
            "location": "village",
            "is_optional": false,
            "prerequisites": []
        }},
        {{
            "id": "obj_002",
            "description": "Second objective description",
            "objective_type": "kill",
            "target": "enemy_name",
            "target_count": 3,
            "location": "dark_forest",
            "is_optional": false,
            "prerequisites": ["obj_001"]
        }}
    ]
}}

Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_ENEMIES = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
VALID LOCATIONS: {zones}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

For this step, generate enemy encounters. Include at least one boss enemy.

Difficulty stat guide:
- easy: HP 20-50, damage 3-8. Boss: HP 60-120, damage 8-16
- medium: HP 40-100, damage 5-15. Boss: HP 120-250, damage 12-30
- hard: HP 80-200, damage 10-25. Boss: HP 200-500, damage 20-50

Valid narrative roles: guardian, roaming, ambush, boss

You MUST respond with ONLY this JSON object and nothing else:
{{
    "component": "enemies",
    "enemies": [
        {{
            "id": "enemy_001",
            "enemy_type": "skeleton",
            "display_name": "Skeleton Warrior",
            "hp": 45,
            "damage": 8,
            "location": "graveyard",
            "count": 3,
            "is_boss": false,
            "loot_table": ["bone_fragment", "rusty_sword"],
            "narrative_role": "roaming"
        }},
        {{
            "id": "enemy_002",
            "enemy_type": "lich",
            "display_name": "The Lich King",
            "hp": 200,
            "damage": 25,
            "location": "ancient_ruins",
            "count": 1,
            "is_boss": true,
            "loot_table": ["lich_staff", "soul_gem"],
            "narrative_role": "boss"
        }}
    ]
}}

Generate {max_enemies} or fewer enemies. Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_SUBQUESTS = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
QUEST ID: {quest_id}
VALID LOCATIONS: {zones}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

For this step, generate sub-quests (side objectives that connect to the main storyline).

Valid sub-quest types: fetch, collect, deliver, escort, puzzle
Valid objective types: collect, kill, deliver, explore, escort, interact
Valid item types: weapon, armor, consumable, key_item, currency

You MUST respond with ONLY this JSON object and nothing else:
{{
    "component": "subquests",
    "sub_quests": [
        {{
            "id": "sq_001",
            "title": "Sub-quest Title",
            "description": "What this sub-quest is about",
            "quest_type": "fetch",
            "parent_quest_id": "{quest_id}",
            "trigger_condition": "When the player completes obj_001",
            "objectives": [
                {{
                    "id": "sq_obj_001",
                    "description": "Sub-quest objective description",
                    "objective_type": "collect",
                    "target": "item_name",
                    "target_count": 3,
                    "location": "village",
                    "is_optional": false,
                    "prerequisites": []
                }}
            ],
            "rewards": [
                {{
                    "item_name": "Health Potion",
                    "item_type": "consumable",
                    "quantity": 2,
                    "stats": null
                }}
            ]
        }}
    ]
}}

Generate at least {min_subquests} sub-quests. Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_DIALOGS = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
VALID LOCATIONS: {zones}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

For this step, generate NPC dialog trees. Each NPC should have a dialog tree with 3-6 nodes and at least one player choice point.

You MUST respond with ONLY this JSON object and nothing else:
{{
    "component": "dialogs",
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
                    "text": "Greetings, traveler. I have urgent news.",
                    "next_node": "explain",
                    "choices": null
                }},
                {{
                    "node_id": "explain",
                    "speaker": "Elder Moira",
                    "text": "Dark forces threaten our village. Will you help?",
                    "next_node": null,
                    "choices": [
                        {{
                            "text": "I will help you.",
                            "next_node": "accept",
                            "consequence": null
                        }},
                        {{
                            "text": "What is the reward?",
                            "next_node": "negotiate",
                            "consequence": null
                        }}
                    ]
                }},
                {{
                    "node_id": "accept",
                    "speaker": "Elder Moira",
                    "text": "Thank you, brave one!",
                    "next_node": null,
                    "choices": null
                }},
                {{
                    "node_id": "negotiate",
                    "speaker": "Elder Moira",
                    "text": "You will be rewarded handsomely.",
                    "next_node": "accept",
                    "choices": null
                }}
            ]
        }}
    ]
}}

Generate 2-3 NPCs with dialog trees. Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_REWARDS = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

For this step, generate quest rewards appropriate to the difficulty level.

Valid item types: weapon, armor, consumable, key_item, currency

Difficulty guide:
- easy: basic items, 50-150 gold
- medium: good weapons/armor, 150-400 gold
- hard: powerful unique items, 400-1000 gold

You MUST respond with ONLY this JSON object and nothing else:
{{
    "component": "rewards",
    "rewards": [
        {{
            "item_name": "Iron Sword",
            "item_type": "weapon",
            "quantity": 1,
            "stats": {{"damage": 10}}
        }},
        {{
            "item_name": "Gold Coins",
            "item_type": "currency",
            "quantity": 200,
            "stats": null
        }},
        {{
            "item_name": "Health Potion",
            "item_type": "consumable",
            "quantity": 3,
            "stats": null
        }}
    ]
}}

Generate 3-5 rewards. Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_PUZZLES = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
VALID LOCATIONS: {zones}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

For this step, generate 1-2 environmental puzzles that fit the quest theme.

Valid item types for rewards: weapon, armor, consumable, key_item, currency

You MUST respond with ONLY this JSON object and nothing else:
{{
    "component": "puzzles",
    "puzzles": [
        {{
            "id": "puzzle_001",
            "description": "A stone door with three rune slots",
            "location": "ancient_ruins",
            "solution_hint": "The runes are scattered on nearby pillars",
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

Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_LORE_AND_EVENTS = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
QUEST ID: {quest_id}
VALID LOCATIONS: {zones}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

For this step, generate lore items, dynamic events, and branching consequences.

You MUST respond with ONLY this JSON object and nothing else:
{{
    "component": "lore_and_events",
    "lore_items": [
        {{
            "id": "lore_001",
            "title": "Ancient Scroll Fragment",
            "content": "The text tells of a time when spirits roamed freely...",
            "location": "dark_forest",
            "related_quest_id": "{quest_id}"
        }}
    ],
    "dynamic_events": [
        {{
            "id": "event_001",
            "trigger": "player_enters_dark_forest",
            "description": "An eerie mist rolls in",
            "effects": ["reduce_visibility", "spawn_ambient_sounds"],
            "narrative_text": "A cold mist wraps around you..."
        }}
    ],
    "branching_consequences": [
        {{
            "id": "branch_001",
            "trigger_choice": "spare_the_enemy_leader",
            "description": "Sparing the leader changes the village attitude",
            "world_changes": ["enemy_camp_becomes_ally"],
            "reputation_effect": 1,
            "unlocks_quest": null,
            "blocks_quest": null
        }}
    ]
}}

Generate 2-3 lore items, 1-2 dynamic events, and 1-2 branching consequences.
Respond with ONLY the JSON object above. No other text."""


EXECUTE_STEP_GENERIC = """Execute this quest generation step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
VALID LOCATIONS: {zones}

YOUR PLAN:
{plan_text}

CURRENT STEP: Step {step_number} - "{step_description}"

RESULTS FROM PREVIOUS STEPS:
{prior_results}

Based on the step description above, generate the appropriate quest content as a JSON object.

You MUST respond with ONLY a valid JSON object. The JSON object must have a "component" key with a string value describing what this step produces, plus the relevant data.

Respond with ONLY the JSON object. No other text."""


SYNTHESIS_PROMPT = """You are assembling a complete quest from individual components that were generated step by step.

TASK: {description}
THEME: {theme}
DIFFICULTY: {difficulty}
QUEST ID: {quest_id}
VALID LOCATIONS: {zones}

ALL GENERATED COMPONENTS:
{all_results}

Review all the components above and assemble them into one complete, coherent quest. Fix any inconsistencies between components (e.g., locations, names, IDs that don't match).

You MUST respond with ONLY this JSON object and nothing else:
{{
    "title": "Quest Title",
    "description": "2-3 sentence quest summary",
    "storyline": ["Act 1: ...", "Act 2: ...", "Act 3: ..."],
    "objectives": [
        {{
            "id": "obj_001",
            "description": "Objective description",
            "objective_type": "explore",
            "target": "target_name",
            "target_count": 1,
            "location": "village",
            "is_optional": false,
            "prerequisites": []
        }}
    ],
    "enemies": [
        {{
            "id": "enemy_001",
            "enemy_type": "type",
            "display_name": "Display Name",
            "hp": 50,
            "damage": 10,
            "location": "dark_forest",
            "count": 2,
            "is_boss": false,
            "loot_table": ["item1"],
            "narrative_role": "roaming"
        }}
    ],
    "sub_quests": [
        {{
            "id": "sq_001",
            "title": "Sub-quest Title",
            "description": "Description",
            "quest_type": "fetch",
            "parent_quest_id": "{quest_id}",
            "trigger_condition": "When condition is met",
            "objectives": [
                {{
                    "id": "sq_obj_001",
                    "description": "Sub objective",
                    "objective_type": "collect",
                    "target": "item",
                    "target_count": 1,
                    "location": "village",
                    "is_optional": false,
                    "prerequisites": []
                }}
            ],
            "rewards": [
                {{
                    "item_name": "Item",
                    "item_type": "consumable",
                    "quantity": 1,
                    "stats": null
                }}
            ]
        }}
    ],
    "npc_dialogs": [
        {{
            "npc_id": "npc_001",
            "npc_name": "NPC Name",
            "location": "village",
            "entry_node": "greeting",
            "dialog_tree": [
                {{
                    "node_id": "greeting",
                    "speaker": "NPC Name",
                    "text": "Dialog text here.",
                    "next_node": null,
                    "choices": null
                }}
            ]
        }}
    ],
    "rewards": [
        {{
            "item_name": "Item Name",
            "item_type": "weapon",
            "quantity": 1,
            "stats": {{"damage": 10}}
        }}
    ],
    "puzzles": [
        {{
            "id": "puzzle_001",
            "description": "Puzzle description",
            "location": "ancient_ruins",
            "solution_hint": "Hint text",
            "required_items": ["item1"],
            "reward": {{
                "item_name": "Puzzle Reward",
                "item_type": "key_item",
                "quantity": 1,
                "stats": null
            }},
            "unlocks": "area_name"
        }}
    ],
    "lore_items": [
        {{
            "id": "lore_001",
            "title": "Lore Title",
            "content": "Lore text content.",
            "location": "dark_forest",
            "related_quest_id": "{quest_id}"
        }}
    ],
    "dynamic_events": [
        {{
            "id": "event_001",
            "trigger": "trigger_condition",
            "description": "Event description",
            "effects": ["effect1"],
            "narrative_text": "What the player sees."
        }}
    ],
    "branching_consequences": [
        {{
            "id": "branch_001",
            "trigger_choice": "choice_name",
            "description": "Consequence description",
            "world_changes": ["change1"],
            "reputation_effect": 1,
            "unlocks_quest": null,
            "blocks_quest": null
        }}
    ]
}}

Make sure ALL locations are from this valid list: {zones}
Respond with ONLY the JSON object above. No other text."""


# Keywords used to classify which component a plan step is about
COMPONENT_KEYWORDS = {
    "storyline": ["storyline", "story", "title", "narrative", "description", "act", "plot", "theme", "setting"],
    "objectives": ["objective", "goal", "task", "mission", "quest objective"],
    "enemies": ["enemy", "enemies", "encounter", "monster", "boss", "combat", "fight", "creature"],
    "subquests": ["sub-quest", "subquest", "side quest", "side objective", "optional quest", "sub quest"],
    "dialogs": ["dialog", "dialogue", "npc", "conversation", "speech", "talk", "character interaction"],
    "rewards": ["reward", "loot", "treasure", "prize", "gold", "item reward", "compensation"],
    "puzzles": ["puzzle", "riddle", "environmental", "mechanism", "lock", "challenge"],
    "lore_and_events": ["lore", "event", "branch", "consequence", "world-building", "dynamic", "collectible"],
}
