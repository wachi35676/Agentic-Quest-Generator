"""Reflection pattern for quest generation.

Holistic generate-reflect-revise loop:
  Phase 1 (Draft):   Generate the entire quest in one shot.
  Phase 2 (Reflect): Present the full quest back to the LLM for structured critique.
  Phase 3 (Revise):  Feed quest + critique back and ask for an improved version.

Phases 2-3 repeat for CONFIG.reflection_max_rounds iterations.

Key difference from Critic: Reflection is HOLISTIC (whole quest at once).
Critic is GRANULAR (each component gets individual adversarial review).
"""

import json
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
from .prompts.reflection_prompts import (
    SYSTEM_PROMPT, DRAFT_PROMPT, REFLECT_PROMPT, REVISE_PROMPT,
)


class ReflectionPattern(AgenticPattern):
    """Reflection pattern: Draft -> Reflect -> Revise loop.

    Generates the complete quest holistically, then iteratively
    improves it through self-critique and revision rounds.
    """

    @property
    def pattern_name(self) -> str:
        return "reflection"

    def generate(self, task: GenerationTask, world_state: WorldState = None) -> QuestData:
        """Generate a complete quest using the Reflection loop."""
        tracer = self._create_tracer(task)
        start_time = time.time()
        quest_id = f"quest_{uuid.uuid4().hex[:8]}"
        llm_calls = 0
        total_tokens = 0
        max_rounds = self.config.get("reflection_max_rounds", CONFIG.reflection_max_rounds)
        zones = ", ".join(CONFIG.world_zones)

        # ---------------------------------------------------------------
        # Phase 1: DRAFT — generate the entire quest in one shot
        # ---------------------------------------------------------------
        tracer.log(
            step_type="decision",
            metadata={"phase": "draft", "thought": "Generating the complete quest in a single LLM call."},
        )

        draft_prompt = DRAFT_PROMPT.format(
            description=task.description,
            theme=task.theme,
            difficulty=task.difficulty,
            required_elements=", ".join(task.required_elements) if task.required_elements else "none",
            constraints=str(task.constraints) if task.constraints else "none",
            zones=zones,
            quest_id=quest_id,
        )

        quest_dict = self._call_llm_with_repair(
            prompt=draft_prompt,
            step_label="draft",
            tracer=tracer,
        )
        llm_calls_delta, tokens_delta = self._last_call_stats
        llm_calls += llm_calls_delta
        total_tokens += tokens_delta

        if quest_dict is None:
            # Complete failure — return a minimal skeleton
            tracer.log(step_type="error", metadata={"phase": "draft", "error": "Failed to generate draft quest"})
            duration = time.time() - start_time
            return self._empty_quest(quest_id, task, tracer.trace_id, duration, llm_calls, total_tokens)

        # Inject quest_id into the draft (LLM may have invented its own)
        quest_dict["id"] = quest_id

        tracer.log(
            step_type="decision",
            metadata={
                "phase": "draft",
                "observation": "Draft quest generated successfully.",
                "title": quest_dict.get("title", ""),
                "num_objectives": len(quest_dict.get("objectives", [])),
                "num_enemies": len(quest_dict.get("enemies", [])),
            },
        )

        # ---------------------------------------------------------------
        # Phases 2-3: REFLECT and REVISE for K rounds
        # ---------------------------------------------------------------
        for round_num in range(1, max_rounds + 1):
            tracer.log(
                step_type="decision",
                metadata={
                    "phase": "reflect",
                    "round": round_num,
                    "thought": f"Starting reflection round {round_num}/{max_rounds}.",
                },
            )

            quest_json_str = json.dumps(quest_dict, indent=2)

            # --- Phase 2: REFLECT ---
            reflect_prompt = REFLECT_PROMPT.format(quest_json=quest_json_str)

            critique_dict = self._call_llm_with_repair(
                prompt=reflect_prompt,
                step_label=f"reflect_round_{round_num}",
                tracer=tracer,
            )
            llm_calls_delta, tokens_delta = self._last_call_stats
            llm_calls += llm_calls_delta
            total_tokens += tokens_delta

            if critique_dict is None:
                tracer.log(
                    step_type="error",
                    metadata={
                        "phase": "reflect",
                        "round": round_num,
                        "error": "Failed to parse critique — skipping this round.",
                    },
                )
                continue

            tracer.log(
                step_type="decision",
                metadata={
                    "phase": "reflect",
                    "round": round_num,
                    "overall_quality": critique_dict.get("overall_quality", "unknown"),
                    "num_issues": len(critique_dict.get("issues", [])),
                    "missing_elements": critique_dict.get("missing_elements", []),
                },
            )

            # If the critique says "excellent" with no critical/moderate issues, stop early
            issues = critique_dict.get("issues", [])
            severe_issues = [i for i in issues if i.get("severity") in ("critical", "moderate")]
            if critique_dict.get("overall_quality") == "excellent" and len(severe_issues) == 0:
                tracer.log(
                    step_type="decision",
                    metadata={
                        "phase": "reflect",
                        "round": round_num,
                        "thought": "Quest rated excellent with no critical/moderate issues. Stopping early.",
                    },
                )
                break

            # --- Phase 3: REVISE ---
            tracer.log(
                step_type="decision",
                metadata={
                    "phase": "revise",
                    "round": round_num,
                    "thought": f"Revising quest to address {len(severe_issues)} critical/moderate issues.",
                },
            )

            critique_json_str = json.dumps(critique_dict, indent=2)
            revise_prompt = REVISE_PROMPT.format(
                quest_json=quest_json_str,
                critique_json=critique_json_str,
                zones=zones,
            )

            revised_dict = self._call_llm_with_repair(
                prompt=revise_prompt,
                step_label=f"revise_round_{round_num}",
                tracer=tracer,
            )
            llm_calls_delta, tokens_delta = self._last_call_stats
            llm_calls += llm_calls_delta
            total_tokens += tokens_delta

            if revised_dict is None:
                tracer.log(
                    step_type="error",
                    metadata={
                        "phase": "revise",
                        "round": round_num,
                        "error": "Failed to parse revised quest — keeping previous version.",
                    },
                )
                continue

            # Ensure quest_id stays consistent
            revised_dict["id"] = quest_id
            quest_dict = revised_dict

            tracer.log(
                step_type="decision",
                metadata={
                    "phase": "revise",
                    "round": round_num,
                    "observation": "Revision applied successfully.",
                    "title": quest_dict.get("title", ""),
                    "num_objectives": len(quest_dict.get("objectives", [])),
                    "num_enemies": len(quest_dict.get("enemies", [])),
                },
            )

        # ---------------------------------------------------------------
        # Assemble final QuestData
        # ---------------------------------------------------------------
        duration = time.time() - start_time
        quest = self._assemble_quest(quest_dict, quest_id, task, tracer.trace_id, duration, llm_calls, total_tokens)

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

        stats = tracer.get_stats()
        tracer.log(step_type="decision", metadata={"final_stats": stats})

        return quest

    def adapt(self, adaptation_task: AdaptationTask) -> QuestModification:
        """Adapt a quest using the Reflection pattern: Generate -> Reflect -> Revise.

        Uses a single draft, one reflection, and one revision (3 LLM calls)
        for low-latency adaptation.
        """
        quest = adaptation_task.current_quest
        event_type = adaptation_task.event_type
        event_details = adaptation_task.event_details
        game_state = adaptation_task.game_state
        zones = ", ".join(CONFIG.world_zones)

        quest_summary = self._build_quest_summary_for_adapt(quest)
        game_state_str = self._format_game_state_for_adapt(game_state)

        # --- Phase 1: DRAFT modification ---
        draft_prompt = (
            f"You are adapting a quest in real-time based on a game event.\n\n"
            f"QUEST SUMMARY:\n{quest_summary}\n\n"
            f"GAME STATE:\n{game_state_str}\n\n"
            f"EVENT: {event_type}\n"
            f"EVENT DETAILS: {json.dumps(event_details)}\n\n"
            f"Valid zones: {zones}\n\n"
            f"Generate a quest modification as a JSON object with these fields:\n"
            f'{{"modified_objectives": [' + '{"id": "existing_obj_id", "description": "updated text", "target": "new_target", "target_count": 1, "location": "zone_name"}' + '],\n'
            f'"added_objectives": [' + '{"id": "obj_new_01", "description": "text", "objective_type": "kill|collect|explore|interact", "target": "target_name", "target_count": 1, "location": "zone_name"}' + '],\n'
            f'"removed_objective_ids": [],\n'
            f'"added_enemies": [' + '{"id": "enemy_new_01", "enemy_type": "type", "display_name": "Name", "hp": 50, "damage": 10, "location": "zone_name", "count": 1, "is_boss": false, "loot_table": [], "narrative_role": "roaming"}' + '],\n'
            f'"removed_enemy_ids": [],\n'
            f'"added_dialogs": [],\n'
            f'"narrative_update": "A narrative beat describing the story shift.",\n'
            f'"reason": "Why this modification was made."}}\n\n'
            f"Respond with ONLY the JSON object."
        )

        draft_dict = self._call_llm_with_repair(
            prompt=draft_prompt,
            step_label="adapt_draft",
            tracer=TraceLogger(task_id="adapt", pattern=self.pattern_name),
        )

        if draft_dict is None:
            return QuestModification(
                narrative_update=f"The winds of fate shift as {event_type.replace('_', ' ')} occurs...",
                reason=f"Reflection adaptation fallback for {event_type}",
            )

        # --- Phase 2: REFLECT on the draft ---
        draft_json_str = json.dumps(draft_dict, indent=2)
        reflect_prompt = (
            f"Review this quest modification for quality:\n\n"
            f"EVENT: {event_type}\n"
            f"MODIFICATION:\n{draft_json_str}\n\n"
            f"QUEST CONTEXT:\n{quest_summary}\n\n"
            f"Evaluate:\n"
            f"1. Is the narrative_update engaging and relevant to the event?\n"
            f"2. Are the added objectives achievable and interesting?\n"
            f"3. Are enemy stats balanced for the quest difficulty ({quest.difficulty})?\n"
            f"4. Does the modification make narrative sense given the event?\n\n"
            f"Respond with a JSON object:\n"
            f'{{"quality": "good|needs_improvement", '
            f'"issues": ["issue1", "issue2"], '
            f'"suggestions": ["suggestion1", "suggestion2"]}}'
        )

        reflect_dict = self._call_llm_with_repair(
            prompt=reflect_prompt,
            step_label="adapt_reflect",
            tracer=TraceLogger(task_id="adapt", pattern=self.pattern_name),
        )

        # If reflection says it's good, or we can't parse reflection, use draft
        if reflect_dict is None or reflect_dict.get("quality") == "good":
            return self._dict_to_modification(draft_dict, event_type)

        # --- Phase 3: REVISE based on reflection ---
        issues = reflect_dict.get("issues", [])
        suggestions = reflect_dict.get("suggestions", [])
        feedback = "\n".join(f"- {i}" for i in issues + suggestions)

        revise_prompt = (
            f"Revise this quest modification based on feedback:\n\n"
            f"ORIGINAL MODIFICATION:\n{draft_json_str}\n\n"
            f"FEEDBACK:\n{feedback}\n\n"
            f"EVENT: {event_type}\n"
            f"QUEST CONTEXT:\n{quest_summary}\n\n"
            f"Valid zones: {zones}\n\n"
            f"Respond with the improved JSON modification object. Same format as original.\n"
            f"Respond with ONLY the JSON object."
        )

        revised_dict = self._call_llm_with_repair(
            prompt=revise_prompt,
            step_label="adapt_revise",
            tracer=TraceLogger(task_id="adapt", pattern=self.pattern_name),
        )

        if revised_dict is not None:
            return self._dict_to_modification(revised_dict, event_type)

        return self._dict_to_modification(draft_dict, event_type)

    @staticmethod
    def _dict_to_modification(d: dict, event_type: str) -> QuestModification:
        """Convert a parsed dict to a QuestModification."""
        return QuestModification(
            modified_objectives=d.get("modified_objectives", []),
            added_objectives=d.get("added_objectives", []),
            removed_objective_ids=d.get("removed_objective_ids", []),
            added_enemies=d.get("added_enemies", []),
            removed_enemy_ids=d.get("removed_enemy_ids", []),
            added_dialogs=d.get("added_dialogs", []),
            narrative_update=d.get("narrative_update", ""),
            reason=d.get("reason", f"Reflection adaptation for {event_type}"),
        )

    @staticmethod
    def _build_quest_summary_for_adapt(quest) -> str:
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

    @staticmethod
    def _format_game_state_for_adapt(game_state: dict) -> str:
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

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    # Tracks (llm_calls, tokens) for the most recent _call_llm_with_repair
    _last_call_stats: tuple[int, int] = (0, 0)

    def _call_llm_with_repair(
        self,
        prompt: str,
        step_label: str,
        tracer: TraceLogger,
    ) -> dict | None:
        """Call the LLM and attempt JSON extraction with retries.

        Sets self._last_call_stats = (llm_calls, total_tokens) as a side-effect
        so the caller can accumulate totals.

        Returns the parsed dict, or None if all attempts fail.
        """
        llm_calls = 0
        total_tokens = 0
        current_prompt = prompt

        for attempt in range(CONFIG.json_repair_max_attempts):
            response: LLMResponse = self.llm.generate(
                prompt=current_prompt,
                system=SYSTEM_PROMPT,
                temperature=CONFIG.default_temperature,
            )
            llm_calls += 1
            total_tokens += response.prompt_tokens + response.completion_tokens

            tracer.log(
                step_type="llm_call",
                prompt=current_prompt[:500] + "..." if len(current_prompt) > 500 else current_prompt,
                response=response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
                duration_ms=response.duration_ms,
                tokens_estimate={"input": response.prompt_tokens, "output": response.completion_tokens},
                metadata={"step_label": step_label, "attempt": attempt + 1},
            )

            if not response.success:
                tracer.log(
                    step_type="error",
                    metadata={"step_label": step_label, "error": response.error, "attempt": attempt + 1},
                )
                continue

            parsed = extract_json(response.text)
            if parsed is not None and isinstance(parsed, dict):
                tracer.log(
                    step_type="parse",
                    parsed_json=parsed,
                    parse_success=True,
                    metadata={"step_label": step_label, "attempt": attempt + 1},
                )
                self._last_call_stats = (llm_calls, total_tokens)
                return parsed

            # Parse failed — log and retry with a repair hint
            tracer.log(
                step_type="repair",
                response=response.text[:500],
                parse_success=False,
                metadata={"step_label": step_label, "attempt": attempt + 1},
            )
            current_prompt = (
                "Your previous response was not valid JSON. "
                "Please try again. Respond with ONLY a JSON object — no markdown, no explanation.\n\n"
                + prompt
            )

        self._last_call_stats = (llm_calls, total_tokens)
        return None

    def _assemble_quest(
        self,
        quest_dict: dict,
        quest_id: str,
        task: GenerationTask,
        trace_id: str,
        duration: float,
        llm_calls: int,
        total_tokens: int,
    ) -> QuestData:
        """Convert a raw quest dict into a validated QuestData instance."""
        # Ensure parent_quest_id is set on all sub-quests
        for sq in quest_dict.get("sub_quests", []):
            sq["parent_quest_id"] = quest_id

        return QuestData(
            id=quest_id,
            title=quest_dict.get("title", "Untitled Quest"),
            description=quest_dict.get("description", ""),
            theme=task.theme,
            difficulty=task.difficulty,
            storyline=quest_dict.get("storyline", []),
            objectives=self._parse_list(quest_dict.get("objectives", []), QuestObjective),
            enemies=self._parse_list(quest_dict.get("enemies", []), EnemyEncounter),
            sub_quests=self._parse_list(quest_dict.get("sub_quests", []), SubQuest),
            npc_dialogs=self._parse_list(quest_dict.get("npc_dialogs", []), NPCDialog),
            rewards=self._parse_list(quest_dict.get("rewards", []), Reward),
            puzzles=self._parse_list(quest_dict.get("puzzles", []), EnvironmentalPuzzle),
            lore_items=self._parse_list(quest_dict.get("lore_items", []), LoreItem),
            dynamic_events=self._parse_list(quest_dict.get("dynamic_events", []), DynamicEvent),
            branching_consequences=self._parse_list(quest_dict.get("branching_consequences", []), BranchingConsequence),
            generated_by=self.pattern_name,
            generation_trace_id=trace_id,
            generation_duration_seconds=duration,
            llm_calls_count=llm_calls,
            total_tokens_estimate=total_tokens,
        )

    @staticmethod
    def _parse_list(raw: list[dict], cls) -> list:
        """Safely parse a list of dicts into dataclass instances using from_dict."""
        result = []
        for d in raw:
            try:
                result.append(cls.from_dict(d))
            except (KeyError, TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _empty_quest(
        quest_id: str,
        task: GenerationTask,
        trace_id: str,
        duration: float,
        llm_calls: int,
        total_tokens: int,
    ) -> QuestData:
        """Return a minimal empty quest when generation completely fails."""
        return QuestData(
            id=quest_id,
            title="Generation Failed",
            description="The reflection pattern failed to generate a quest.",
            theme=task.theme,
            difficulty=task.difficulty,
            storyline=["Generation failed — no storyline produced."],
            generated_by="reflection",
            generation_trace_id=trace_id,
            generation_duration_seconds=duration,
            llm_calls_count=llm_calls,
            total_tokens_estimate=total_tokens,
        )
