"""Quest validation — ensures generated quests are structurally sound."""

from dataclasses import dataclass, field
from config import CONFIG
from .schema import QuestData


@dataclass
class ValidationResult:
    """Result of validating a quest."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Validation score: 1.0 = perfect, 0.0 = all checks failed."""
        total_checks = len(self.errors) + len(self.warnings) + 1
        return max(0.0, 1.0 - len(self.errors) / total_checks)


def validate_quest(quest: QuestData) -> ValidationResult:
    """Validate a QuestData instance for structural correctness.

    Checks:
    1. Required minimums (objectives, enemies, NPCs, rewards)
    2. Location references against world zones
    3. Objective prerequisite references
    4. Dialog tree integrity
    5. Enemy stat bounds
    6. Sub-quest parent references
    """
    errors = []
    warnings = []
    valid_zones = set(CONFIG.world_zones)
    valid_objective_ids = {o.id for o in quest.objectives}
    for sq in quest.sub_quests:
        valid_objective_ids.update(o.id for o in sq.objectives)

    # 1. Required minimums
    if not quest.objectives:
        errors.append("Quest must have at least 1 objective")
    if not quest.enemies:
        warnings.append("Quest has no enemy encounters")
    if not quest.npc_dialogs:
        warnings.append("Quest has no NPC dialogs")
    if not quest.rewards:
        warnings.append("Quest has no rewards")
    if not quest.storyline:
        errors.append("Quest must have a storyline with at least 1 narrative beat")
    if not quest.title:
        errors.append("Quest must have a title")
    if not quest.description:
        errors.append("Quest must have a description")

    # 2. Location references
    all_locations = set()
    for obj in quest.objectives:
        if obj.location:
            all_locations.add(obj.location)
    for enemy in quest.enemies:
        if enemy.location:
            all_locations.add(enemy.location)
    for npc in quest.npc_dialogs:
        if npc.location:
            all_locations.add(npc.location)
    for puzzle in quest.puzzles:
        if puzzle.location:
            all_locations.add(puzzle.location)
    for lore in quest.lore_items:
        if lore.location:
            all_locations.add(lore.location)

    invalid_locations = all_locations - valid_zones
    if invalid_locations:
        warnings.append(f"Unknown locations (not in world zones): {invalid_locations}")

    # 3. Objective prerequisites
    for obj in quest.objectives:
        for prereq in obj.prerequisites:
            if prereq not in valid_objective_ids:
                errors.append(f"Objective '{obj.id}' has invalid prerequisite '{prereq}'")

    # 4. Dialog tree integrity
    for npc_dialog in quest.npc_dialogs:
        node_ids = {dl.node_id for dl in npc_dialog.dialog_tree}
        if npc_dialog.entry_node and npc_dialog.entry_node not in node_ids:
            errors.append(
                f"NPC '{npc_dialog.npc_name}' entry_node '{npc_dialog.entry_node}' not found in dialog tree"
            )
        for dl in npc_dialog.dialog_tree:
            if dl.next_node and dl.next_node not in node_ids:
                warnings.append(
                    f"Dialog node '{dl.node_id}' references unknown next_node '{dl.next_node}'"
                )
            if dl.choices:
                for choice in dl.choices:
                    if choice.next_node not in node_ids:
                        warnings.append(
                            f"Dialog choice in '{dl.node_id}' references unknown node '{choice.next_node}'"
                        )

    # 5. Enemy stat bounds
    for enemy in quest.enemies:
        if enemy.hp < 1 or enemy.hp > 9999:
            warnings.append(f"Enemy '{enemy.display_name}' HP ({enemy.hp}) out of expected range [1-9999]")
        if enemy.damage < 0 or enemy.damage > 999:
            warnings.append(f"Enemy '{enemy.display_name}' damage ({enemy.damage}) out of expected range [0-999]")
        if enemy.count < 1:
            errors.append(f"Enemy '{enemy.display_name}' count must be >= 1")

    # 6. Sub-quest parent references
    for sq in quest.sub_quests:
        if sq.parent_quest_id and sq.parent_quest_id != quest.id:
            warnings.append(
                f"Sub-quest '{sq.id}' parent_quest_id '{sq.parent_quest_id}' "
                f"doesn't match quest id '{quest.id}'"
            )

    # 7. Difficulty validation
    if quest.difficulty not in ("easy", "medium", "hard"):
        warnings.append(f"Unknown difficulty '{quest.difficulty}' — expected easy/medium/hard")

    # 8. Theme validation
    if not quest.theme:
        warnings.append("Quest has no theme set")

    is_valid = len(errors) == 0
    return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)
