"""Quest data schema — the central data contract.

All five agentic patterns produce QuestData. The game consumes it.
The evaluator scores it. Everything flows through these types.
"""

from dataclasses import dataclass, field
from typing import Any
import json


@dataclass
class DialogChoice:
    """A player dialog choice leading to a different dialog node."""
    text: str
    next_node: str  # ID of next DialogLine node
    consequence: str | None = None  # e.g. "reputation+1", "unlock_subquest_sq01"

    def to_dict(self) -> dict:
        return {"text": self.text, "next_node": self.next_node, "consequence": self.consequence}

    @classmethod
    def from_dict(cls, d: dict) -> "DialogChoice":
        return cls(text=d["text"], next_node=d["next_node"], consequence=d.get("consequence"))


@dataclass
class DialogLine:
    """A single node in a dialog tree."""
    node_id: str
    speaker: str  # NPC name or "player"
    text: str
    next_node: str | None = None  # Next node ID, or None for end
    choices: list[DialogChoice] | None = None

    def to_dict(self) -> dict:
        d = {"node_id": self.node_id, "speaker": self.speaker, "text": self.text, "next_node": self.next_node}
        if self.choices:
            d["choices"] = [c.to_dict() for c in self.choices]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DialogLine":
        choices = None
        if d.get("choices"):
            choices = [DialogChoice.from_dict(c) for c in d["choices"]]
        return cls(
            node_id=d["node_id"], speaker=d["speaker"], text=d["text"],
            next_node=d.get("next_node"), choices=choices,
        )


@dataclass
class NPCDialog:
    """A dialog tree for an NPC."""
    npc_id: str
    npc_name: str
    location: str
    dialog_tree: list[DialogLine] = field(default_factory=list)
    entry_node: str = ""

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id, "npc_name": self.npc_name,
            "location": self.location, "entry_node": self.entry_node,
            "dialog_tree": [dl.to_dict() for dl in self.dialog_tree],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NPCDialog":
        tree = [DialogLine.from_dict(dl) for dl in d.get("dialog_tree", [])]
        return cls(
            npc_id=d["npc_id"], npc_name=d["npc_name"],
            location=d["location"], entry_node=d.get("entry_node", ""),
            dialog_tree=tree,
        )


@dataclass
class Reward:
    """An item or currency reward."""
    item_name: str
    item_type: str  # "weapon" | "armor" | "consumable" | "key_item" | "currency"
    quantity: int = 1
    stats: dict[str, int] | None = None  # {"damage": 5} or {"defense": 3}

    def to_dict(self) -> dict:
        return {"item_name": self.item_name, "item_type": self.item_type,
                "quantity": self.quantity, "stats": self.stats}

    @classmethod
    def from_dict(cls, d: dict) -> "Reward":
        return cls(item_name=d["item_name"], item_type=d["item_type"],
                   quantity=d.get("quantity", 1), stats=d.get("stats"))


@dataclass
class QuestObjective:
    """A single quest objective."""
    id: str
    description: str
    objective_type: str  # "collect" | "kill" | "deliver" | "explore" | "escort" | "interact"
    target: str
    target_count: int = 1
    location: str = ""
    is_optional: bool = False
    completed: bool = False
    prerequisites: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "objective_type": self.objective_type, "target": self.target,
            "target_count": self.target_count, "location": self.location,
            "is_optional": self.is_optional, "completed": self.completed,
            "prerequisites": self.prerequisites,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QuestObjective":
        return cls(
            id=d["id"], description=d["description"],
            objective_type=d["objective_type"], target=d["target"],
            target_count=d.get("target_count", 1), location=d.get("location", ""),
            is_optional=d.get("is_optional", False), completed=d.get("completed", False),
            prerequisites=d.get("prerequisites", []),
        )


@dataclass
class EnemyEncounter:
    """An enemy encounter definition."""
    id: str
    enemy_type: str
    display_name: str
    hp: int
    damage: int
    location: str
    count: int = 1
    is_boss: bool = False
    loot_table: list[str] = field(default_factory=list)
    narrative_role: str = "roaming"  # "guardian" | "roaming" | "ambush" | "boss"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "enemy_type": self.enemy_type,
            "display_name": self.display_name, "hp": self.hp,
            "damage": self.damage, "location": self.location,
            "count": self.count, "is_boss": self.is_boss,
            "loot_table": self.loot_table, "narrative_role": self.narrative_role,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EnemyEncounter":
        return cls(
            id=d["id"], enemy_type=d["enemy_type"],
            display_name=d["display_name"], hp=d["hp"],
            damage=d["damage"], location=d["location"],
            count=d.get("count", 1), is_boss=d.get("is_boss", False),
            loot_table=d.get("loot_table", []),
            narrative_role=d.get("narrative_role", "roaming"),
        )


@dataclass
class SubQuest:
    """A sub-quest linked to the main quest."""
    id: str
    title: str
    description: str
    quest_type: str  # "fetch" | "collect" | "deliver" | "escort" | "puzzle"
    objectives: list[QuestObjective] = field(default_factory=list)
    rewards: list[Reward] = field(default_factory=list)
    parent_quest_id: str = ""
    trigger_condition: str = ""  # When this sub-quest becomes available
    dialogs: list[NPCDialog] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "quest_type": self.quest_type, "parent_quest_id": self.parent_quest_id,
            "trigger_condition": self.trigger_condition,
            "objectives": [o.to_dict() for o in self.objectives],
            "rewards": [r.to_dict() for r in self.rewards],
            "dialogs": [d.to_dict() for d in self.dialogs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SubQuest":
        return cls(
            id=d["id"], title=d["title"], description=d["description"],
            quest_type=d["quest_type"], parent_quest_id=d.get("parent_quest_id", ""),
            trigger_condition=d.get("trigger_condition", ""),
            objectives=[QuestObjective.from_dict(o) for o in d.get("objectives", [])],
            rewards=[Reward.from_dict(r) for r in d.get("rewards", [])],
            dialogs=[NPCDialog.from_dict(dl) for dl in d.get("dialogs", [])],
        )


@dataclass
class EnvironmentalPuzzle:
    """A puzzle in the game world."""
    id: str
    description: str
    location: str
    solution_hint: str = ""
    required_items: list[str] = field(default_factory=list)
    reward: Reward | None = None
    unlocks: str | None = None  # What solving it opens

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "location": self.location, "solution_hint": self.solution_hint,
            "required_items": self.required_items,
            "reward": self.reward.to_dict() if self.reward else None,
            "unlocks": self.unlocks,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EnvironmentalPuzzle":
        reward = Reward.from_dict(d["reward"]) if d.get("reward") else None
        return cls(
            id=d["id"], description=d["description"],
            location=d["location"], solution_hint=d.get("solution_hint", ""),
            required_items=d.get("required_items", []),
            reward=reward, unlocks=d.get("unlocks"),
        )


@dataclass
class LoreItem:
    """A world-building lore collectible."""
    id: str
    title: str
    content: str
    location: str
    related_quest_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "content": self.content,
            "location": self.location, "related_quest_id": self.related_quest_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LoreItem":
        return cls(
            id=d["id"], title=d["title"], content=d["content"],
            location=d["location"], related_quest_id=d.get("related_quest_id"),
        )


@dataclass
class DynamicEvent:
    """An event triggered by player actions or game state."""
    id: str
    trigger: str  # "player_kills_3_spiders" | "enters_zone_dark_forest" etc.
    description: str
    effects: list[str] = field(default_factory=list)  # "spawn_enemy_ambush" etc.
    narrative_text: str = ""  # What the player sees/hears

    def to_dict(self) -> dict:
        return {
            "id": self.id, "trigger": self.trigger, "description": self.description,
            "effects": self.effects, "narrative_text": self.narrative_text,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DynamicEvent":
        return cls(
            id=d["id"], trigger=d["trigger"], description=d["description"],
            effects=d.get("effects", []), narrative_text=d.get("narrative_text", ""),
        )


@dataclass
class BranchingConsequence:
    """A consequence of a player choice that affects the world."""
    id: str
    trigger_choice: str  # Dialog choice or action that triggers this
    description: str
    world_changes: list[str] = field(default_factory=list)
    reputation_effect: int = 0  # -2 to +2
    unlocks_quest: str | None = None
    blocks_quest: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "trigger_choice": self.trigger_choice,
            "description": self.description, "world_changes": self.world_changes,
            "reputation_effect": self.reputation_effect,
            "unlocks_quest": self.unlocks_quest, "blocks_quest": self.blocks_quest,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BranchingConsequence":
        return cls(
            id=d["id"], trigger_choice=d["trigger_choice"],
            description=d["description"], world_changes=d.get("world_changes", []),
            reputation_effect=d.get("reputation_effect", 0),
            unlocks_quest=d.get("unlocks_quest"), blocks_quest=d.get("blocks_quest"),
        )


@dataclass
class QuestData:
    """Top-level quest structure. Every agentic pattern produces this."""
    id: str
    title: str
    description: str
    theme: str
    difficulty: str  # "easy" | "medium" | "hard"
    storyline: list[str] = field(default_factory=list)  # Ordered narrative beats
    objectives: list[QuestObjective] = field(default_factory=list)
    enemies: list[EnemyEncounter] = field(default_factory=list)
    sub_quests: list[SubQuest] = field(default_factory=list)
    npc_dialogs: list[NPCDialog] = field(default_factory=list)
    rewards: list[Reward] = field(default_factory=list)
    puzzles: list[EnvironmentalPuzzle] = field(default_factory=list)
    lore_items: list[LoreItem] = field(default_factory=list)
    dynamic_events: list[DynamicEvent] = field(default_factory=list)
    branching_consequences: list[BranchingConsequence] = field(default_factory=list)
    # Generation metadata
    generated_by: str = ""  # "react" | "reflection" | "tot" | "critic" | "plan_execute"
    generation_trace_id: str = ""
    generation_duration_seconds: float = 0.0
    llm_calls_count: int = 0
    total_tokens_estimate: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "theme": self.theme, "difficulty": self.difficulty,
            "storyline": self.storyline,
            "objectives": [o.to_dict() for o in self.objectives],
            "enemies": [e.to_dict() for e in self.enemies],
            "sub_quests": [sq.to_dict() for sq in self.sub_quests],
            "npc_dialogs": [d.to_dict() for d in self.npc_dialogs],
            "rewards": [r.to_dict() for r in self.rewards],
            "puzzles": [p.to_dict() for p in self.puzzles],
            "lore_items": [l.to_dict() for l in self.lore_items],
            "dynamic_events": [de.to_dict() for de in self.dynamic_events],
            "branching_consequences": [bc.to_dict() for bc in self.branching_consequences],
            "generated_by": self.generated_by,
            "generation_trace_id": self.generation_trace_id,
            "generation_duration_seconds": self.generation_duration_seconds,
            "llm_calls_count": self.llm_calls_count,
            "total_tokens_estimate": self.total_tokens_estimate,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QuestData":
        return cls(
            id=d["id"], title=d["title"], description=d["description"],
            theme=d["theme"], difficulty=d["difficulty"],
            storyline=d.get("storyline", []),
            objectives=[QuestObjective.from_dict(o) for o in d.get("objectives", [])],
            enemies=[EnemyEncounter.from_dict(e) for e in d.get("enemies", [])],
            sub_quests=[SubQuest.from_dict(sq) for sq in d.get("sub_quests", [])],
            npc_dialogs=[NPCDialog.from_dict(dl) for dl in d.get("npc_dialogs", [])],
            rewards=[Reward.from_dict(r) for r in d.get("rewards", [])],
            puzzles=[EnvironmentalPuzzle.from_dict(p) for p in d.get("puzzles", [])],
            lore_items=[LoreItem.from_dict(l) for l in d.get("lore_items", [])],
            dynamic_events=[DynamicEvent.from_dict(de) for de in d.get("dynamic_events", [])],
            branching_consequences=[BranchingConsequence.from_dict(bc) for bc in d.get("branching_consequences", [])],
            generated_by=d.get("generated_by", ""),
            generation_trace_id=d.get("generation_trace_id", ""),
            generation_duration_seconds=d.get("generation_duration_seconds", 0.0),
            llm_calls_count=d.get("llm_calls_count", 0),
            total_tokens_estimate=d.get("total_tokens_estimate", 0),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "QuestData":
        return cls.from_dict(json.loads(json_str))

    def save(self, filepath: str):
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, filepath: str) -> "QuestData":
        with open(filepath, encoding="utf-8") as f:
            return cls.from_json(f.read())
