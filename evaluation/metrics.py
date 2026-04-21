"""Automated structural metrics for quest evaluation.

Computes quantitative metrics from a QuestData instance without
requiring any LLM calls. These metrics measure completeness,
structural validity, complexity, branching, and internal consistency.
"""

from quests.schema import QuestData
from quests.validator import validate_quest


# Required fields that should be non-empty for a complete quest
_REQUIRED_FIELDS = [
    "id", "title", "description", "theme", "difficulty",
    "storyline", "objectives", "enemies", "sub_quests",
    "npc_dialogs", "rewards", "puzzles", "lore_items",
    "dynamic_events", "branching_consequences",
]


def _completeness_score(quest: QuestData) -> float:
    """Fraction of required fields that are non-empty (0-1)."""
    filled = 0
    total = len(_REQUIRED_FIELDS)
    for fname in _REQUIRED_FIELDS:
        val = getattr(quest, fname, None)
        if val is None:
            continue
        if isinstance(val, str) and val:
            filled += 1
        elif isinstance(val, list) and len(val) > 0:
            filled += 1
        elif isinstance(val, (int, float)) and val:
            filled += 1
    return filled / total if total > 0 else 0.0


def _structural_validity(quest: QuestData) -> float:
    """Run validate_quest and return the score (0-1)."""
    result = validate_quest(quest)
    return result.score


def _complexity_score(quest: QuestData) -> float:
    """Weighted sum measuring quest richness.

    Weights:
        objectives * 1.0
        enemies * 0.5
        sub_quests * 2.0
        dialog_nodes * 0.3
        puzzles * 1.5
        lore_items * 0.5
        dynamic_events * 1.0
        branching_consequences * 1.5
    """
    dialog_node_count = sum(
        len(d.dialog_tree) for d in quest.npc_dialogs
    )
    score = (
        len(quest.objectives) * 1.0
        + len(quest.enemies) * 0.5
        + len(quest.sub_quests) * 2.0
        + dialog_node_count * 0.3
        + len(quest.puzzles) * 1.5
        + len(quest.lore_items) * 0.5
        + len(quest.dynamic_events) * 1.0
        + len(quest.branching_consequences) * 1.5
    )
    return score


def _branching_factor(quest: QuestData) -> int:
    """Count of player choice points.

    Counts DialogChoice nodes across all NPC dialogs plus
    BranchingConsequence entries.
    """
    choice_count = 0
    for npc_dialog in quest.npc_dialogs:
        for node in npc_dialog.dialog_tree:
            if node.choices:
                choice_count += len(node.choices)
    choice_count += len(quest.branching_consequences)
    return choice_count


def _interconnectedness(quest: QuestData) -> float:
    """Ratio of cross-references found to total possible references.

    Checks how many components reference other components:
    - Objective prerequisites referencing other objective IDs
    - Sub-quest parent_quest_id referencing the main quest
    - Dialog choices with consequences referencing quests/objectives
    - Puzzles that unlock something
    - BranchingConsequences that unlock/block quests
    - Dynamic events with effects referencing other components
    - Lore items related to quest IDs
    """
    total_possible = 0
    references_found = 0

    # Objective prerequisites
    for obj in quest.objectives:
        total_possible += 1
        if obj.prerequisites:
            references_found += 1

    # Sub-quest parent references
    for sq in quest.sub_quests:
        total_possible += 1
        if sq.parent_quest_id:
            references_found += 1

    # Dialog choice consequences
    for npc_dialog in quest.npc_dialogs:
        for node in npc_dialog.dialog_tree:
            if node.choices:
                for choice in node.choices:
                    total_possible += 1
                    if choice.consequence:
                        references_found += 1

    # Puzzles unlocking something
    for puzzle in quest.puzzles:
        total_possible += 1
        if puzzle.unlocks:
            references_found += 1

    # Branching consequences unlocking/blocking quests
    for bc in quest.branching_consequences:
        total_possible += 1
        if bc.unlocks_quest or bc.blocks_quest:
            references_found += 1

    # Dynamic events with effects
    for event in quest.dynamic_events:
        total_possible += 1
        if event.effects:
            references_found += 1

    # Lore items with related quest
    for lore in quest.lore_items:
        total_possible += 1
        if lore.related_quest_id:
            references_found += 1

    return references_found / total_possible if total_possible > 0 else 0.0


def _internal_consistency(quest: QuestData) -> float:
    """Check that all IDs, locations, and prerequisites resolve correctly (0-1).

    Verifies:
    - All objective prerequisite IDs exist
    - All dialog next_node IDs exist within the same dialog tree
    - All dialog entry_node IDs exist
    - Sub-quest parent_quest_id matches quest.id (if set)
    - BranchingConsequence unlock/block quest IDs exist
    """
    checks = 0
    passed = 0

    # Collect all known IDs
    all_objective_ids = {o.id for o in quest.objectives}
    for sq in quest.sub_quests:
        all_objective_ids.update(o.id for o in sq.objectives)
    all_quest_ids = {quest.id}
    all_quest_ids.update(sq.id for sq in quest.sub_quests)

    # Check objective prerequisites
    for obj in quest.objectives:
        for prereq in obj.prerequisites:
            checks += 1
            if prereq in all_objective_ids:
                passed += 1

    # Check dialog tree integrity
    for npc_dialog in quest.npc_dialogs:
        node_ids = {dl.node_id for dl in npc_dialog.dialog_tree}

        # Entry node
        if npc_dialog.entry_node:
            checks += 1
            if npc_dialog.entry_node in node_ids:
                passed += 1

        # Next-node references
        for dl in npc_dialog.dialog_tree:
            if dl.next_node:
                checks += 1
                if dl.next_node in node_ids:
                    passed += 1
            if dl.choices:
                for choice in dl.choices:
                    checks += 1
                    if choice.next_node in node_ids:
                        passed += 1

    # Sub-quest parent references
    for sq in quest.sub_quests:
        if sq.parent_quest_id:
            checks += 1
            if sq.parent_quest_id == quest.id:
                passed += 1

    # BranchingConsequence quest references
    for bc in quest.branching_consequences:
        if bc.unlocks_quest:
            checks += 1
            if bc.unlocks_quest in all_quest_ids:
                passed += 1
        if bc.blocks_quest:
            checks += 1
            if bc.blocks_quest in all_quest_ids:
                passed += 1

    return passed / checks if checks > 0 else 1.0


def _component_counts(quest: QuestData) -> dict:
    """Raw counts of each component type."""
    dialog_nodes = sum(len(d.dialog_tree) for d in quest.npc_dialogs)
    return {
        "storyline_beats": len(quest.storyline),
        "objectives": len(quest.objectives),
        "enemies": len(quest.enemies),
        "sub_quests": len(quest.sub_quests),
        "npc_dialogs": len(quest.npc_dialogs),
        "dialog_nodes": dialog_nodes,
        "rewards": len(quest.rewards),
        "puzzles": len(quest.puzzles),
        "lore_items": len(quest.lore_items),
        "dynamic_events": len(quest.dynamic_events),
        "branching_consequences": len(quest.branching_consequences),
    }


def compute_structural_metrics(quest: QuestData) -> dict:
    """Compute all structural metrics for a quest.

    Returns a dict with keys:
        completeness_score (float 0-1)
        structural_validity (float 0-1)
        complexity_score (float)
        branching_factor (int)
        interconnectedness (float 0-1)
        internal_consistency (float 0-1)
        component_counts (dict)
    """
    return {
        "completeness_score": _completeness_score(quest),
        "structural_validity": _structural_validity(quest),
        "complexity_score": _complexity_score(quest),
        "branching_factor": _branching_factor(quest),
        "interconnectedness": _interconnectedness(quest),
        "internal_consistency": _internal_consistency(quest),
        "component_counts": _component_counts(quest),
    }
