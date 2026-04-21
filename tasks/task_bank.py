"""Pre-defined generation tasks for testing and evaluation."""

from agents.base import GenerationTask


TASKS = {
    "dark_forest_medium": GenerationTask(
        task_id="dark_forest_medium",
        theme="dark_forest",
        difficulty="medium",
        description=(
            "Create a quest set in a dark, ancient forest. A village elder asks the hero "
            "to investigate why animals have been acting strangely near the forest's heart. "
            "The quest should reveal a corrupted nature spirit as the source and include "
            "forest-themed enemies, at least one sub-quest involving a lost traveler, "
            "and environmental puzzles using forest elements."
        ),
        required_elements=["boss_fight", "lost_npc_rescue", "environmental_puzzle"],
        constraints={"max_enemies": 8, "min_subquests": 1},
    ),
    "undead_crypt_hard": GenerationTask(
        task_id="undead_crypt_hard",
        theme="cave_system",
        difficulty="hard",
        description=(
            "Create a quest centered around an ancient crypt beneath the mountains. "
            "A necromancer has awakened the dead and threatens the nearby village. "
            "The hero must descend into the crypt, face undead horrors, solve ancient "
            "riddles left by the crypt's builders, and confront the necromancer. "
            "Include a moral choice about whether to destroy or seal the crypt."
        ),
        required_elements=["boss_fight", "moral_choice", "ancient_riddle", "npc_betrayal"],
        constraints={"max_enemies": 12, "min_subquests": 2},
    ),
    "village_easy": GenerationTask(
        task_id="village_easy",
        theme="village",
        difficulty="easy",
        description=(
            "Create a simple introductory quest in a peaceful village. The village "
            "blacksmith needs materials to forge a special weapon. The hero must "
            "gather iron ore from a nearby mine and herbs from the forest edge. "
            "Include friendly NPCs, simple fetch objectives, and light combat "
            "with wildlife."
        ),
        required_elements=["fetch_quest", "crafting_reward"],
        constraints={"max_enemies": 4, "min_subquests": 1},
    ),
    "bandit_hideout_medium": GenerationTask(
        task_id="bandit_hideout_medium",
        theme="mountain_pass",
        difficulty="medium",
        description=(
            "Create a quest about a bandit gang terrorizing trade routes through "
            "a mountain pass. The merchant guild hires the hero to infiltrate or "
            "assault the bandit camp. Include options for stealth or combat approaches, "
            "a charismatic bandit leader, and a twist where some bandits are actually "
            "displaced villagers."
        ),
        required_elements=["boss_fight", "moral_choice", "stealth_option"],
        constraints={"max_enemies": 10, "min_subquests": 1},
    ),
    "ancient_ruins_hard": GenerationTask(
        task_id="ancient_ruins_hard",
        theme="ancient_ruins",
        difficulty="hard",
        description=(
            "Create a quest exploring ancient ruins of a forgotten civilization. "
            "A scholar believes the ruins contain a powerful artifact that could "
            "either save or doom the realm. The hero must navigate traps, solve "
            "puzzles based on ancient lore, fight guardians left behind, and "
            "ultimately decide the artifact's fate. Include rich lore items "
            "throughout the ruins."
        ),
        required_elements=["boss_fight", "environmental_puzzle", "lore_heavy", "moral_choice"],
        constraints={"max_enemies": 10, "min_subquests": 2},
    ),
    "swamp_witch_medium": GenerationTask(
        task_id="swamp_witch_medium",
        theme="swamp",
        difficulty="medium",
        description=(
            "Create a quest set in a murky swamp where villagers have been "
            "disappearing. Rumors point to a witch living deep in the marsh. "
            "The hero must navigate treacherous terrain, deal with swamp creatures, "
            "and discover the witch is actually protecting the villagers from a "
            "greater threat lurking beneath the water. Include potion-crafting "
            "mechanics and a choice to ally with or oppose the witch."
        ),
        required_elements=["boss_fight", "moral_choice", "crafting_mechanic"],
        constraints={"max_enemies": 8, "min_subquests": 1},
    ),
    "castle_siege_hard": GenerationTask(
        task_id="castle_siege_hard",
        theme="castle",
        difficulty="hard",
        description=(
            "Create a quest where the hero must help defend or reclaim a castle "
            "under siege by a rival lord's army. Include multiple phases: scouting "
            "enemy positions, rallying defenders, sabotaging siege equipment, and "
            "a final confrontation in the throne room. Add political intrigue with "
            "a traitor among the defenders and NPCs with conflicting loyalties."
        ),
        required_elements=["boss_fight", "npc_betrayal", "stealth_option", "moral_choice"],
        constraints={"max_enemies": 15, "min_subquests": 3},
    ),
    "marketplace_theft_easy": GenerationTask(
        task_id="marketplace_theft_easy",
        theme="marketplace",
        difficulty="easy",
        description=(
            "Create a quest in a bustling marketplace where a merchant's prized "
            "goods have been stolen. The hero must question witnesses, follow clues "
            "through market stalls, and track down the thief. The thief turns out "
            "to be a hungry orphan. Include dialog-heavy investigation and a choice "
            "about how to handle the child."
        ),
        required_elements=["investigation", "moral_choice"],
        constraints={"max_enemies": 2, "min_subquests": 1},
    ),
    "graveyard_medium": GenerationTask(
        task_id="graveyard_medium",
        theme="graveyard",
        difficulty="medium",
        description=(
            "Create a quest set in an old graveyard on the edge of town. A priest "
            "reports that graves have been disturbed and ghostly lights seen at night. "
            "The hero investigates and discovers a grieving alchemist trying to "
            "resurrect a loved one, inadvertently raising lesser undead. Include "
            "ghost encounters, grave-robbing puzzles, and a sympathetic antagonist."
        ),
        required_elements=["boss_fight", "environmental_puzzle", "moral_choice"],
        constraints={"max_enemies": 7, "min_subquests": 1},
    ),
    "river_crossing_easy": GenerationTask(
        task_id="river_crossing_easy",
        theme="river_crossing",
        difficulty="easy",
        description=(
            "Create a quest at a river crossing where the bridge has been destroyed "
            "by a storm. Travelers are stranded on both sides. The hero must help "
            "repair the bridge, deal with river creatures attacking workers, and "
            "escort a caravan safely across. Include a subplot about a rivalry "
            "between two ferrymen competing for business."
        ),
        required_elements=["escort_mission", "fetch_quest"],
        constraints={"max_enemies": 5, "min_subquests": 1},
    ),
    "abandoned_mine_medium": GenerationTask(
        task_id="abandoned_mine_medium",
        theme="abandoned_mine",
        difficulty="medium",
        description=(
            "Create a quest in an abandoned mine that has been sealed for decades. "
            "Miners recently broke through to a new chamber and awakened something "
            "ancient. The hero must descend through progressively more dangerous "
            "mine levels, rescue trapped miners, solve mechanical puzzles involving "
            "mine equipment, and confront a crystal golem at the deepest level."
        ),
        required_elements=["boss_fight", "lost_npc_rescue", "environmental_puzzle"],
        constraints={"max_enemies": 9, "min_subquests": 2},
    ),
    "tower_wizard_hard": GenerationTask(
        task_id="tower_wizard_hard",
        theme="tower",
        difficulty="hard",
        description=(
            "Create a quest involving a wizard's tower that has gone haywire. "
            "The wizard's experiments have torn open portals to other planes, "
            "and creatures are pouring through. The hero must ascend the tower "
            "floor by floor, each with a different planar theme (fire, ice, shadow). "
            "Include logic puzzles, elemental enemies, and a final choice about "
            "whether to help the wizard close the portals or seize the power."
        ),
        required_elements=["boss_fight", "environmental_puzzle", "moral_choice", "lore_heavy"],
        constraints={"max_enemies": 12, "min_subquests": 2},
    ),
    "dark_forest_easy": GenerationTask(
        task_id="dark_forest_easy",
        theme="dark_forest",
        difficulty="easy",
        description=(
            "Create a simple quest where the hero must gather rare moonflowers "
            "that only bloom at night in the dark forest. An herbalist needs them "
            "to cure a sick child. Include encounters with nocturnal wildlife, "
            "a friendly forest spirit who offers guidance, and a simple navigation "
            "puzzle using stars and landmarks."
        ),
        required_elements=["fetch_quest", "environmental_puzzle"],
        constraints={"max_enemies": 3, "min_subquests": 0},
    ),
    "cave_dragon_hard": GenerationTask(
        task_id="cave_dragon_hard",
        theme="cave_system",
        difficulty="hard",
        description=(
            "Create an epic quest where a dragon has made its lair in a vast "
            "cave system. The dragon demands tribute or it will destroy the "
            "nearest town. The hero must explore the caves, find the dragon's "
            "weakness through ancient texts and NPC knowledge, potentially "
            "recruit allies, and confront the dragon. Include multiple possible "
            "endings: slay, negotiate, or trick the dragon."
        ),
        required_elements=["boss_fight", "moral_choice", "lore_heavy", "ally_recruitment"],
        constraints={"max_enemies": 14, "min_subquests": 3},
    ),
    "village_festival_easy": GenerationTask(
        task_id="village_festival_easy",
        theme="village",
        difficulty="easy",
        description=(
            "Create a lighthearted quest during a village harvest festival. "
            "The hero helps organize events: a cooking contest, an archery "
            "tournament, and a treasure hunt. Trouble arises when a traveling "
            "trickster starts cheating and causing mischief. Include fun "
            "minigame-style objectives and lots of NPC dialog."
        ),
        required_elements=["investigation", "fetch_quest"],
        constraints={"max_enemies": 1, "min_subquests": 2},
    ),
    "mountain_pass_hard": GenerationTask(
        task_id="mountain_pass_hard",
        theme="mountain_pass",
        difficulty="hard",
        description=(
            "Create a quest involving a treacherous mountain pass during winter. "
            "An avalanche has blocked the only trade route and stranded a "
            "diplomatic envoy carrying a peace treaty. The hero must navigate "
            "blizzards, fight ice elementals, rescue survivors from the avalanche, "
            "and uncover a plot to sabotage the peace treaty. Include survival "
            "mechanics, multiple factions, and branching consequences."
        ),
        required_elements=["boss_fight", "escort_mission", "npc_betrayal", "moral_choice"],
        constraints={"max_enemies": 11, "min_subquests": 2},
    ),
    "swamp_treasure_easy": GenerationTask(
        task_id="swamp_treasure_easy",
        theme="swamp",
        difficulty="easy",
        description=(
            "Create a quest where a treasure map leads the hero into the swamp. "
            "An old pirate left clues pointing to buried loot. The hero must "
            "follow cryptic riddles, avoid swamp hazards like quicksand and "
            "leeches, and deal with other treasure hunters also following the map. "
            "Include simple puzzles based on the riddles and light combat."
        ),
        required_elements=["environmental_puzzle", "fetch_quest"],
        constraints={"max_enemies": 4, "min_subquests": 1},
    ),
    "ancient_ruins_medium": GenerationTask(
        task_id="ancient_ruins_medium",
        theme="ancient_ruins",
        difficulty="medium",
        description=(
            "Create a quest where the hero discovers ruins that were recently "
            "exposed by an earthquake. A local historian believes the ruins hold "
            "records of a lost magical art. The hero must explore rooms filled "
            "with guardian constructs, decode inscriptions, and piece together "
            "fragments of a spell. Include a rival adventuring party competing "
            "for the same prize."
        ),
        required_elements=["boss_fight", "environmental_puzzle", "lore_heavy"],
        constraints={"max_enemies": 8, "min_subquests": 1},
    ),
    "graveyard_hard": GenerationTask(
        task_id="graveyard_hard",
        theme="graveyard",
        difficulty="hard",
        description=(
            "Create a quest where an ancient vampire lord awakens beneath the "
            "graveyard. The vampire begins converting townsfolk into thralls. "
            "The hero must investigate disappearances, discover the vampire's "
            "identity among the town's respected citizens, find holy relics "
            "scattered across multiple locations, and confront the vampire in "
            "its underground lair. Include branching consequences based on "
            "which townsfolk are saved or lost."
        ),
        required_elements=["boss_fight", "investigation", "moral_choice", "npc_betrayal"],
        constraints={"max_enemies": 13, "min_subquests": 3},
    ),
    "tower_heist_medium": GenerationTask(
        task_id="tower_heist_medium",
        theme="tower",
        difficulty="medium",
        description=(
            "Create a quest where the hero must infiltrate a noble's tower to "
            "steal evidence of corruption. The tower is heavily guarded with "
            "both soldiers and magical wards. The hero can approach through "
            "stealth, disguise, or brute force. Include floor-by-floor challenges, "
            "a safe-cracking puzzle, guard patrol patterns to memorize, and an "
            "NPC informant inside the tower who may or may not be trustworthy."
        ),
        required_elements=["stealth_option", "environmental_puzzle", "npc_betrayal"],
        constraints={"max_enemies": 8, "min_subquests": 1},
    ),
}


def get_task(task_id: str) -> GenerationTask:
    """Get a generation task by ID."""
    if task_id not in TASKS:
        available = ", ".join(TASKS.keys())
        raise ValueError(f"Unknown task '{task_id}'. Available: {available}")
    return TASKS[task_id]


def get_all_tasks() -> list[GenerationTask]:
    """Get all generation tasks."""
    return list(TASKS.values())
