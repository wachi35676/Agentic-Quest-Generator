"""Runtime adapter bridging game events to the agentic pattern for quest adaptation."""

import time
import uuid

from quests.schema import (
    QuestData, QuestObjective, EnemyEncounter, NPCDialog, DialogLine,
    DialogChoice,
)
from agents.base import AgenticPattern, AdaptationTask, QuestModification
from runtime.events import AdaptationEvent, GameStateSnapshot
from runtime.threading_utils import BackgroundTask


# Minimum seconds between adaptations
ADAPTATION_COOLDOWN = 30.0


class RuntimeAdapter:
    """Bridges game events to the agentic pattern's adapt() method.

    - Receives game events and decides which ones warrant quest adaptation.
    - Packages the game state + current quest + event into an AdaptationTask.
    - Calls the selected agentic pattern's adapt() method in a background thread.
    - Returns QuestModification to be applied to the active quest.
    - Manages a queue of pending adaptations (don't stack multiple at once).
    - Has a cooldown (minimum 30 seconds between adaptations).
    """

    def __init__(self, pattern: AgenticPattern):
        self.pattern = pattern
        self._last_adaptation_time: float = 0.0
        self._pending_task: BackgroundTask | None = None
        self._completed_modification: QuestModification | None = None
        self._adaptation_count: int = 0

    def on_event(
        self,
        event: AdaptationEvent,
        game_state: GameStateSnapshot,
        current_quest: QuestData,
    ):
        """Called by the game engine when a relevant event occurs.

        Decides whether to trigger an adaptation based on:
        - Whether an adaptation is already in progress
        - Whether the cooldown has elapsed
        - Whether the event is significant enough
        """
        # Don't stack adaptations
        if self.has_pending_adaptation():
            return

        # Check cooldown
        now = time.time()
        elapsed = now - self._last_adaptation_time
        if elapsed < ADAPTATION_COOLDOWN and not event.is_high_priority:
            return

        # Build the AdaptationTask
        task = AdaptationTask(
            current_quest=current_quest,
            event_type=event.event_type,
            event_details=event.details,
            game_state=game_state.to_dict(),
        )

        # Launch adaptation in background thread
        self._pending_task = BackgroundTask(self.pattern.adapt, task)
        self._pending_task.start()
        self._last_adaptation_time = now

    def has_pending_adaptation(self) -> bool:
        """Check if an adaptation is currently in progress."""
        if self._pending_task is None:
            return False
        if self._pending_task.is_done():
            # Move result to completed
            error = self._pending_task.get_error()
            if error is None:
                self._completed_modification = self._pending_task.get_result()
            else:
                # Adaptation failed; discard silently
                self._completed_modification = None
            self._pending_task = None
            return False
        return True

    def get_completed_adaptation(self) -> QuestModification | None:
        """Get and clear the completed adaptation result, if any."""
        # Check if pending task just finished
        self.has_pending_adaptation()

        if self._completed_modification is not None:
            result = self._completed_modification
            self._completed_modification = None
            self._adaptation_count += 1
            return result
        return None

    @staticmethod
    def apply_modification(quest: QuestData, modification: QuestModification) -> list[str]:
        """Apply a QuestModification to a QuestData instance.

        Returns a list of human-readable messages describing changes made.
        """
        messages = []

        # Add new objectives
        for obj_dict in modification.added_objectives:
            try:
                # Ensure unique ID
                if "id" not in obj_dict:
                    obj_dict["id"] = f"obj_adapt_{uuid.uuid4().hex[:6]}"
                obj = QuestObjective.from_dict(obj_dict)
                quest.objectives.append(obj)
                messages.append(f"New objective: {obj.description}")
            except (KeyError, TypeError, ValueError):
                continue

        # Remove objectives
        if modification.removed_objective_ids:
            before = len(quest.objectives)
            quest.objectives = [
                o for o in quest.objectives
                if o.id not in modification.removed_objective_ids
            ]
            removed = before - len(quest.objectives)
            if removed > 0:
                messages.append(f"{removed} objective(s) removed.")

        # Modify existing objectives
        for mod_dict in modification.modified_objectives:
            obj_id = mod_dict.get("id", "")
            for obj in quest.objectives:
                if obj.id == obj_id:
                    if "description" in mod_dict:
                        obj.description = mod_dict["description"]
                    if "target" in mod_dict:
                        obj.target = mod_dict["target"]
                    if "target_count" in mod_dict:
                        obj.target_count = mod_dict["target_count"]
                    if "location" in mod_dict:
                        obj.location = mod_dict["location"]
                    if "is_optional" in mod_dict:
                        obj.is_optional = mod_dict["is_optional"]
                    messages.append(f"Objective updated: {obj.description}")
                    break

        # Add new enemies
        for enemy_dict in modification.added_enemies:
            try:
                if "id" not in enemy_dict:
                    enemy_dict["id"] = f"enemy_adapt_{uuid.uuid4().hex[:6]}"
                enemy = EnemyEncounter.from_dict(enemy_dict)
                quest.enemies.append(enemy)
                messages.append(f"New enemy: {enemy.display_name}")
            except (KeyError, TypeError, ValueError):
                continue

        # Remove enemies
        if modification.removed_enemy_ids:
            before = len(quest.enemies)
            quest.enemies = [
                e for e in quest.enemies
                if e.id not in modification.removed_enemy_ids
            ]
            removed = before - len(quest.enemies)
            if removed > 0:
                messages.append(f"{removed} enemy encounter(s) removed.")

        # Add new dialogs
        for dialog_dict in modification.added_dialogs:
            try:
                dialog = NPCDialog.from_dict(dialog_dict)
                quest.npc_dialogs.append(dialog)
                messages.append(f"New dialog: {dialog.npc_name}")
            except (KeyError, TypeError, ValueError):
                continue

        # Narrative update
        if modification.narrative_update:
            quest.storyline.append(modification.narrative_update)
            messages.append(modification.narrative_update)

        return messages
