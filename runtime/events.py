"""Event types and game state snapshots for real-time quest adaptation."""

from dataclasses import dataclass, field
import time


# --- Event type constants ---

EVENT_NPC_KILLED = "npc_killed"
EVENT_OBJECTIVE_SKIPPED = "objective_skipped"
EVENT_OBJECTIVE_FAILED = "objective_failed"
EVENT_AREA_DISCOVERED = "area_discovered"
EVENT_REPUTATION_THRESHOLD = "reputation_threshold"
EVENT_BRANCHING_CHOICE = "branching_choice"
EVENT_BOSS_DEFEATED = "boss_defeated"
EVENT_ALL_ENEMIES_CLEARED = "all_enemies_cleared"
EVENT_ITEM_ACQUIRED = "item_acquired"

# Set of all valid event types
VALID_EVENT_TYPES = {
    EVENT_NPC_KILLED,
    EVENT_OBJECTIVE_SKIPPED,
    EVENT_OBJECTIVE_FAILED,
    EVENT_AREA_DISCOVERED,
    EVENT_REPUTATION_THRESHOLD,
    EVENT_BRANCHING_CHOICE,
    EVENT_BOSS_DEFEATED,
    EVENT_ALL_ENEMIES_CLEARED,
    EVENT_ITEM_ACQUIRED,
}

# Events that should always trigger adaptation (high priority)
HIGH_PRIORITY_EVENTS = {
    EVENT_NPC_KILLED,
    EVENT_BOSS_DEFEATED,
    EVENT_BRANCHING_CHOICE,
    EVENT_REPUTATION_THRESHOLD,
}

# Events that may trigger adaptation if cooldown allows (normal priority)
NORMAL_PRIORITY_EVENTS = {
    EVENT_OBJECTIVE_SKIPPED,
    EVENT_OBJECTIVE_FAILED,
    EVENT_AREA_DISCOVERED,
    EVENT_ALL_ENEMIES_CLEARED,
    EVENT_ITEM_ACQUIRED,
}


@dataclass
class AdaptationEvent:
    """An event that occurred in the game and may trigger quest adaptation."""
    event_type: str
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {self.event_type}")

    @property
    def is_high_priority(self) -> bool:
        return self.event_type in HIGH_PRIORITY_EVENTS


@dataclass
class GameStateSnapshot:
    """A snapshot of the current game state for context in adaptation."""
    player_hp: int = 100
    player_max_hp: int = 100
    player_position: tuple[int, int] = (0, 0)
    player_inventory: list[dict] = field(default_factory=list)
    player_reputation: int = 0
    completed_objectives: list[str] = field(default_factory=list)
    killed_enemies: dict = field(default_factory=dict)  # enemy_type -> count
    explored_zones: list[str] = field(default_factory=list)
    active_quest_id: str = ""

    def to_dict(self) -> dict:
        return {
            "player_hp": self.player_hp,
            "player_max_hp": self.player_max_hp,
            "player_position": list(self.player_position),
            "player_inventory": [
                {"name": item.get("name", ""), "type": item.get("type", "")}
                for item in self.player_inventory[:10]  # Limit for prompt size
            ],
            "player_reputation": self.player_reputation,
            "completed_objectives": self.completed_objectives,
            "killed_enemies": self.killed_enemies,
            "explored_zones": self.explored_zones,
            "active_quest_id": self.active_quest_id,
        }

    @classmethod
    def from_player(cls, player, quest_data) -> "GameStateSnapshot":
        """Build a snapshot from a Player and QuestData instance."""
        completed = [
            obj.id for obj in quest_data.objectives if obj.completed
        ]
        return cls(
            player_hp=player.hp,
            player_max_hp=player.max_hp,
            player_position=(player.tile_x, player.tile_y),
            player_inventory=list(player.inventory),
            player_reputation=player.reputation,
            completed_objectives=completed,
            killed_enemies=dict(player.kill_counts),
            explored_zones=list(player.explored_zones),
            active_quest_id=quest_data.id,
        )
