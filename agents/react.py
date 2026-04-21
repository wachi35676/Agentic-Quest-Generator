"""ReAct (Reasoning + Acting) pattern for quest generation.

Interleaves Thought/Action/Observation steps to generate quest
components one at a time, building context as it goes.
"""

import time
import uuid

from config import CONFIG
from llm.client import OllamaClient, LLMResponse
from llm.parser import extract_json
from tracing.logger import TraceLogger
from quests.schema import (
    QuestData, QuestObjective, EnemyEncounter, NPCDialog, DialogLine,
    DialogChoice, SubQuest, Reward, EnvironmentalPuzzle, LoreItem,
    DynamicEvent, BranchingConsequence,
)
from quests.validator import validate_quest
from .base import AgenticPattern, GenerationTask, WorldState, AdaptationTask, QuestModification
from .prompts.react_prompts import (
    SYSTEM_PROMPT, COMPONENT_ORDER, COMPONENT_PROMPTS,
)


class ReActPattern(AgenticPattern):
    """ReAct pattern: Thought → Action → Observation loop.

    Generates quest components sequentially. After each component,
    the agent observes what was generated and reasons about what
    to generate next, building on prior context.
    """

    @property
    def pattern_name(self) -> str:
        return "react"

    def generate(self, task: GenerationTask, world_state: WorldState = None) -> QuestData:
        """Generate a complete quest using the ReAct loop."""
        tracer = self._create_tracer(task)
        start_time = time.time()
        quest_id = f"quest_{uuid.uuid4().hex[:8]}"
        llm_calls = 0
        total_tokens = 0

        # Scratchpad accumulates what we've generated so far
        scratchpad = {
            "task": task,
            "quest_id": quest_id,
            "title": "",
            "description": "",
            "storyline": [],
            "objectives": [],
            "enemies": [],
            "sub_quests": [],
            "npc_dialogs": [],
            "rewards": [],
            "puzzles": [],
            "lore_items": [],
            "dynamic_events": [],
            "branching_consequences": [],
        }

        # Step through each component in order
        for component in COMPONENT_ORDER:
            tracer.log(
                step_type="decision",
                metadata={"component": component, "thought": f"Generating {component} next based on what we have so far."},
            )

            # Build the prompt for this component
            prompt = self._build_component_prompt(component, scratchpad, task)

            # Call LLM with repair loop
            parsed = None
            for attempt in range(CONFIG.json_repair_max_attempts):
                response = self.llm.generate(
                    prompt=prompt,
                    system=SYSTEM_PROMPT,
                    temperature=CONFIG.default_temperature,
                )
                llm_calls += 1
                total_tokens += response.prompt_tokens + response.completion_tokens

                tracer.log(
                    step_type="llm_call",
                    prompt=prompt[:500] + "..." if len(prompt) > 500 else prompt,
                    response=response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
                    duration_ms=response.duration_ms,
                    tokens_estimate={"input": response.prompt_tokens, "output": response.completion_tokens},
                    metadata={"component": component, "attempt": attempt + 1},
                )

                if not response.success:
                    tracer.log(step_type="error", metadata={"error": response.error, "component": component})
                    continue

                parsed = extract_json(response.text)
                if parsed is not None:
                    tracer.log(
                        step_type="parse",
                        parsed_json=parsed,
                        parse_success=True,
                        metadata={"component": component},
                    )
                    break
                else:
                    tracer.log(
                        step_type="repair",
                        response=response.text[:500],
                        parse_success=False,
                        metadata={"component": component, "attempt": attempt + 1},
                    )
                    # Add repair hint to prompt
                    prompt = (
                        f"Your previous response was not valid JSON. "
                        f"Please try again. Respond with ONLY a JSON object.\n\n{prompt}"
                    )

            if parsed is None:
                tracer.log(
                    step_type="error",
                    metadata={"component": component, "error": "Failed to parse after all attempts"},
                )
                continue

            # Observation: integrate parsed data into scratchpad
            self._integrate_component(component, parsed, scratchpad)

            tracer.log(
                step_type="decision",
                metadata={
                    "component": component,
                    "observation": f"Successfully generated {component}. Scratchpad updated.",
                },
            )

        # Assemble final QuestData
        duration = time.time() - start_time
        quest = self._assemble_quest(scratchpad, quest_id, tracer.trace_id, duration, llm_calls, total_tokens)

        # Validate
        validation = validate_quest(quest)
        tracer.log(
            step_type="validate",
            metadata={
                "is_valid": validation.is_valid,
                "errors": validation.errors,
                "warnings": validation.warnings,
                "score": validation.score,
            },
        )

        # Save trace stats
        stats = tracer.get_stats()
        tracer.log(step_type="decision", metadata={"final_stats": stats})

        return quest

    def adapt(self, adaptation_task: AdaptationTask) -> QuestModification:
        """Adapt a quest using a simplified 2-3 step ReAct loop.

        Runs a Thought -> Action -> Observation cycle for 2-3 steps,
        focused on the triggering event, then returns a QuestModification.
        """
        quest = adaptation_task.current_quest
        event_type = adaptation_task.event_type
        event_details = adaptation_task.event_details
        game_state = adaptation_task.game_state
        zones = ", ".join(CONFIG.world_zones)

        # Build quest summary for context
        quest_summary = self._build_quest_summary(quest)
        game_state_str = self._format_game_state(game_state)

        # Scratchpad for the ReAct loop
        scratchpad_text = ""

        # Step 1: Thought + Action — analyze the event
        step1_prompt = (
            f"You are adapting a quest in real-time based on a game event.\n\n"
            f"QUEST SUMMARY:\n{quest_summary}\n\n"
            f"GAME STATE:\n{game_state_str}\n\n"
            f"EVENT: {event_type}\n"
            f"EVENT DETAILS: {event_details}\n\n"
            f"Valid zones: {zones}\n\n"
            f"Step 1 - THOUGHT: Analyze what this event means for the quest. "
            f"What should change? Consider the narrative impact.\n"
            f"ACTION: Describe what modifications are needed.\n\n"
            f"Respond with a JSON object:\n"
            f'{{"thought": "your analysis of the event impact", '
            f'"action": "what needs to change in the quest", '
            f'"observation": "what the player would experience"}}'
        )

        response = self.llm.generate(
            prompt=step1_prompt,
            system=SYSTEM_PROMPT,
            temperature=CONFIG.default_temperature,
        )

        step1_parsed = None
        if response.success:
            step1_parsed = extract_json(response.text)

        if step1_parsed:
            thought = step1_parsed.get("thought", "")
            action = step1_parsed.get("action", "")
            observation = step1_parsed.get("observation", "")
            scratchpad_text = (
                f"Step 1 Thought: {thought}\n"
                f"Step 1 Action: {action}\n"
                f"Step 1 Observation: {observation}\n"
            )
        else:
            scratchpad_text = f"Step 1: Event {event_type} occurred. Need to adapt quest.\n"

        # Step 2: Generate the actual QuestModification JSON
        step2_prompt = (
            f"You are adapting a quest in real-time. Based on your analysis:\n\n"
            f"QUEST SUMMARY:\n{quest_summary}\n\n"
            f"EVENT: {event_type}\n"
            f"EVENT DETAILS: {event_details}\n\n"
            f"PRIOR REASONING:\n{scratchpad_text}\n\n"
            f"Valid zones: {zones}\n\n"
            f"Step 2 - Generate the quest modification as a JSON object with these fields:\n"
            f'{{"modified_objectives": [' + '{"id": "existing_obj_id", "description": "updated text", "target": "new_target", "target_count": 1, "location": "zone_name"}' + '],\n'
            f'"added_objectives": [' + '{"id": "obj_new_01", "description": "text", "objective_type": "kill|collect|explore|interact", "target": "target_name", "target_count": 1, "location": "zone_name"}' + '],\n'
            f'"removed_objective_ids": ["obj_id_to_remove"],\n'
            f'"added_enemies": [' + '{"id": "enemy_new_01", "enemy_type": "type", "display_name": "Name", "hp": 50, "damage": 10, "location": "zone_name", "count": 1, "is_boss": false, "loot_table": [], "narrative_role": "roaming"}' + '],\n'
            f'"removed_enemy_ids": [],\n'
            f'"added_dialogs": [],\n'
            f'"narrative_update": "A short narrative beat describing what changed in the story.",\n'
            f'"reason": "Why this modification was made."}}\n\n'
            f"Include ONLY the fields that need changes. Use empty lists for unchanged fields.\n"
            f"Respond with ONLY the JSON object."
        )

        modification = None
        for attempt in range(CONFIG.json_repair_max_attempts):
            response = self.llm.generate(
                prompt=step2_prompt,
                system=SYSTEM_PROMPT,
                temperature=CONFIG.structured_temperature,
            )
            if not response.success:
                continue

            parsed = extract_json(response.text)
            if parsed and isinstance(parsed, dict):
                modification = QuestModification(
                    modified_objectives=parsed.get("modified_objectives", []),
                    added_objectives=parsed.get("added_objectives", []),
                    removed_objective_ids=parsed.get("removed_objective_ids", []),
                    added_enemies=parsed.get("added_enemies", []),
                    removed_enemy_ids=parsed.get("removed_enemy_ids", []),
                    added_dialogs=parsed.get("added_dialogs", []),
                    narrative_update=parsed.get("narrative_update", ""),
                    reason=parsed.get("reason", f"ReAct adaptation for {event_type}"),
                )
                break

            step2_prompt = (
                "Your previous response was not valid JSON. "
                "Please try again. Respond with ONLY a JSON object.\n\n"
                + step2_prompt
            )

        if modification is None:
            modification = QuestModification(
                narrative_update=f"The winds of fate shift as {event_type.replace('_', ' ')} occurs...",
                reason=f"ReAct adaptation fallback for {event_type}",
            )

        return modification

    def _build_quest_summary(self, quest: QuestData) -> str:
        """Build a concise quest summary for adaptation prompts."""
        lines = [
            f"Title: {quest.title}",
            f"Theme: {quest.theme} | Difficulty: {quest.difficulty}",
        ]
        if quest.storyline:
            lines.append(f"Storyline: {' -> '.join(quest.storyline[:3])}")
        if quest.objectives:
            lines.append("Objectives:")
            for obj in quest.objectives:
                status = "DONE" if obj.completed else "active"
                lines.append(f"  - [{obj.id}] {obj.description} ({obj.objective_type}, {status})")
        if quest.enemies:
            lines.append(f"Enemies: {', '.join(e.display_name for e in quest.enemies[:5])}")
        return "\n".join(lines)

    def _format_game_state(self, game_state: dict) -> str:
        """Format game state dict into readable text."""
        lines = []
        hp = game_state.get("player_hp", "?")
        max_hp = game_state.get("player_max_hp", "?")
        lines.append(f"Player HP: {hp}/{max_hp}")
        lines.append(f"Reputation: {game_state.get('player_reputation', 0)}")
        explored = game_state.get("explored_zones", [])
        if explored:
            lines.append(f"Explored zones: {', '.join(explored)}")
        completed = game_state.get("completed_objectives", [])
        if completed:
            lines.append(f"Completed objectives: {', '.join(completed)}")
        kills = game_state.get("killed_enemies", {})
        if kills:
            kill_strs = [f"{k}: {v}" for k, v in kills.items()]
            lines.append(f"Kills: {', '.join(kill_strs)}")
        return "\n".join(lines)

    def _build_component_prompt(self, component: str, scratchpad: dict, task: GenerationTask) -> str:
        """Build the prompt for generating a specific component."""
        template = COMPONENT_PROMPTS[component]
        zones = ", ".join(CONFIG.world_zones)

        # Common format values
        fmt = {
            "description": task.description,
            "theme": task.theme,
            "difficulty": task.difficulty,
            "required_elements": ", ".join(task.required_elements) if task.required_elements else "none",
            "constraints": str(task.constraints),
            "zones": zones,
            "title": scratchpad.get("title", ""),
            "quest_id": scratchpad.get("quest_id", ""),
            "storyline": "\n".join(scratchpad.get("storyline", [])),
            "objectives": self._summarize_objectives(scratchpad.get("objectives", [])),
            "enemies": self._summarize_enemies(scratchpad.get("enemies", [])),
            "max_enemies": task.constraints.get("max_enemies", 8),
            "min_subquests": task.constraints.get("min_subquests", 1),
        }

        return template.format(**fmt)

    def _integrate_component(self, component: str, parsed: dict, scratchpad: dict):
        """Integrate parsed LLM output into the scratchpad."""
        if component == "storyline":
            scratchpad["title"] = parsed.get("title", "Untitled Quest")
            scratchpad["description"] = parsed.get("description", "")
            scratchpad["storyline"] = parsed.get("storyline", [])

        elif component == "objectives":
            scratchpad["objectives"] = parsed.get("objectives", [])

        elif component == "enemies":
            scratchpad["enemies"] = parsed.get("enemies", [])

        elif component == "subquests":
            scratchpad["sub_quests"] = parsed.get("sub_quests", [])

        elif component == "dialogs":
            scratchpad["npc_dialogs"] = parsed.get("npc_dialogs", [])

        elif component == "rewards":
            scratchpad["rewards"] = parsed.get("rewards", [])

        elif component == "puzzles":
            scratchpad["puzzles"] = parsed.get("puzzles", [])

        elif component == "lore_and_events":
            scratchpad["lore_items"] = parsed.get("lore_items", [])
            scratchpad["dynamic_events"] = parsed.get("dynamic_events", [])
            scratchpad["branching_consequences"] = parsed.get("branching_consequences", [])

    def _assemble_quest(
        self, scratchpad: dict, quest_id: str, trace_id: str,
        duration: float, llm_calls: int, total_tokens: int,
    ) -> QuestData:
        """Assemble a QuestData from the scratchpad."""
        return QuestData(
            id=quest_id,
            title=scratchpad.get("title", "Untitled Quest"),
            description=scratchpad.get("description", ""),
            theme=scratchpad["task"].theme,
            difficulty=scratchpad["task"].difficulty,
            storyline=scratchpad.get("storyline", []),
            objectives=self._parse_objectives(scratchpad.get("objectives", [])),
            enemies=self._parse_enemies(scratchpad.get("enemies", [])),
            sub_quests=self._parse_subquests(scratchpad.get("sub_quests", []), quest_id),
            npc_dialogs=self._parse_dialogs(scratchpad.get("npc_dialogs", [])),
            rewards=self._parse_rewards(scratchpad.get("rewards", [])),
            puzzles=self._parse_puzzles(scratchpad.get("puzzles", [])),
            lore_items=self._parse_lore(scratchpad.get("lore_items", [])),
            dynamic_events=self._parse_events(scratchpad.get("dynamic_events", [])),
            branching_consequences=self._parse_branches(scratchpad.get("branching_consequences", [])),
            generated_by=self.pattern_name,
            generation_trace_id=trace_id,
            generation_duration_seconds=duration,
            llm_calls_count=llm_calls,
            total_tokens_estimate=total_tokens,
        )

    # --- Parsing helpers: convert raw dicts to dataclass instances ---

    def _parse_objectives(self, raw: list[dict]) -> list[QuestObjective]:
        result = []
        for d in raw:
            try:
                result.append(QuestObjective.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    def _parse_enemies(self, raw: list[dict]) -> list[EnemyEncounter]:
        result = []
        for d in raw:
            try:
                result.append(EnemyEncounter.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    def _parse_subquests(self, raw: list[dict], quest_id: str) -> list[SubQuest]:
        result = []
        for d in raw:
            try:
                d["parent_quest_id"] = quest_id
                result.append(SubQuest.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    def _parse_dialogs(self, raw: list[dict]) -> list[NPCDialog]:
        result = []
        for d in raw:
            try:
                result.append(NPCDialog.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    def _parse_rewards(self, raw: list[dict]) -> list[Reward]:
        result = []
        for d in raw:
            try:
                result.append(Reward.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    def _parse_puzzles(self, raw: list[dict]) -> list[EnvironmentalPuzzle]:
        result = []
        for d in raw:
            try:
                result.append(EnvironmentalPuzzle.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    def _parse_lore(self, raw: list[dict]) -> list[LoreItem]:
        result = []
        for d in raw:
            try:
                result.append(LoreItem.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    def _parse_events(self, raw: list[dict]) -> list[DynamicEvent]:
        result = []
        for d in raw:
            try:
                result.append(DynamicEvent.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    def _parse_branches(self, raw: list[dict]) -> list[BranchingConsequence]:
        result = []
        for d in raw:
            try:
                result.append(BranchingConsequence.from_dict(d))
            except (KeyError, TypeError):
                continue
        return result

    # --- Summarization helpers for building context in prompts ---

    def _summarize_objectives(self, objectives: list[dict]) -> str:
        if not objectives:
            return "None yet"
        lines = []
        for o in objectives:
            lines.append(f"- [{o.get('id', '?')}] {o.get('description', '?')} ({o.get('objective_type', '?')} at {o.get('location', '?')})")
        return "\n".join(lines)

    def _summarize_enemies(self, enemies: list[dict]) -> str:
        if not enemies:
            return "None yet"
        lines = []
        for e in enemies:
            lines.append(f"- {e.get('display_name', '?')} (HP:{e.get('hp', '?')}, DMG:{e.get('damage', '?')}) at {e.get('location', '?')}")
        return "\n".join(lines)
