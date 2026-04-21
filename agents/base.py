"""Abstract base class for all agentic quest generation patterns."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from llm.client import OllamaClient
from tracing.logger import TraceLogger
from quests.schema import QuestData


@dataclass
class GenerationTask:
    """A quest generation task — input to all patterns."""
    task_id: str
    theme: str  # Must be a valid world zone or thematic descriptor
    difficulty: str  # "easy" | "medium" | "hard"
    description: str  # Human-readable task description for the prompt
    required_elements: list[str] = field(default_factory=list)  # ["boss_fight", "npc_betrayal"]
    constraints: dict = field(default_factory=dict)  # {"max_enemies": 10, "min_subquests": 2}
    seed: int | None = None


@dataclass
class WorldState:
    """Current state of the game world for context-aware generation."""
    available_zones: list[str] = field(default_factory=list)
    player_level: int = 1
    player_reputation: int = 0
    completed_quests: list[str] = field(default_factory=list)
    active_npcs: list[str] = field(default_factory=list)


@dataclass
class AdaptationTask:
    """A request to adapt an existing quest based on a game event."""
    current_quest: QuestData
    event_type: str  # "npc_killed" | "objective_skipped" | "area_discovered" etc.
    event_details: dict = field(default_factory=dict)
    game_state: dict = field(default_factory=dict)  # Player HP, inventory, position, etc.


@dataclass
class QuestModification:
    """A diff describing how a quest was modified during adaptation."""
    modified_objectives: list[dict] = field(default_factory=list)
    added_objectives: list[dict] = field(default_factory=list)
    removed_objective_ids: list[str] = field(default_factory=list)
    added_enemies: list[dict] = field(default_factory=list)
    removed_enemy_ids: list[str] = field(default_factory=list)
    added_dialogs: list[dict] = field(default_factory=list)
    narrative_update: str = ""  # New storyline beat
    reason: str = ""  # Why the modification was made


class AgenticPattern(ABC):
    """Abstract base class for agentic quest generation patterns.

    All five patterns (ReAct, Reflection, ToT, Critic, Plan & Execute)
    implement this interface so they can be compared on the same tasks.
    """

    def __init__(self, llm_client: OllamaClient, config: dict = None):
        self.llm = llm_client
        self.config = config or {}

    @property
    @abstractmethod
    def pattern_name(self) -> str:
        """Name of this pattern for logging and comparison."""
        ...

    @abstractmethod
    def generate(self, task: GenerationTask, world_state: WorldState = None) -> QuestData:
        """Generate a complete quest from a task description.

        This is the pre-generation phase. The pattern runs its full
        reasoning loop to produce a QuestData instance.
        """
        ...

    @abstractmethod
    def adapt(self, adaptation_task: AdaptationTask) -> QuestModification:
        """Adapt an existing quest based on a game event.

        This is the real-time adaptation phase. The pattern runs a
        simplified version of its reasoning loop.
        """
        ...

    def _create_tracer(self, task: GenerationTask) -> TraceLogger:
        """Create a trace logger for this generation run."""
        return TraceLogger(
            task_id=task.task_id,
            pattern=self.pattern_name,
        )
