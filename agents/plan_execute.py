"""Plan & Execute pattern for quest generation.

Step 1 (Plan):  Ask the LLM to create a detailed numbered plan for
                building a quest. The LLM itself decides the decomposition.
Step 2 (Execute): Execute each plan step one by one, passing the plan
                  and all prior results as context.
Step 3 (Replan):  If a step fails or produces poor output, replan
                  (max CONFIG.plan_max_replans replans).
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
from .prompts.plan_execute_prompts import (
    SYSTEM_PROMPT,
    PLAN_PROMPT,
    REPLAN_PROMPT,
    EXECUTE_STEP_STORYLINE,
    EXECUTE_STEP_OBJECTIVES,
    EXECUTE_STEP_ENEMIES,
    EXECUTE_STEP_SUBQUESTS,
    EXECUTE_STEP_DIALOGS,
    EXECUTE_STEP_REWARDS,
    EXECUTE_STEP_PUZZLES,
    EXECUTE_STEP_LORE_AND_EVENTS,
    EXECUTE_STEP_GENERIC,
    SYNTHESIS_PROMPT,
    COMPONENT_KEYWORDS,
)


class PlanExecutePattern(AgenticPattern):
    """Plan & Execute pattern: Plan -> Execute each step -> Replan if needed.

    The key distinction from other patterns is that the LLM itself
    decides how to decompose the quest generation task into steps,
    rather than following a hardcoded component order.
    """

    @property
    def pattern_name(self) -> str:
        return "plan_execute"

    def generate(self, task: GenerationTask, world_state: WorldState = None) -> QuestData:
        """Generate a complete quest using Plan & Execute."""
        tracer = self._create_tracer(task)
        start_time = time.time()
        quest_id = f"quest_{uuid.uuid4().hex[:8]}"
        llm_calls = 0
        total_tokens = 0
        replans_used = 0

        zones = ", ".join(CONFIG.world_zones)
        fmt_base = {
            "description": task.description,
            "theme": task.theme,
            "difficulty": task.difficulty,
            "required_elements": ", ".join(task.required_elements) if task.required_elements else "none",
            "constraints": str(task.constraints),
            "zones": zones,
            "quest_id": quest_id,
            "max_steps": CONFIG.plan_max_steps,
            "max_enemies": task.constraints.get("max_enemies", 8),
            "min_subquests": task.constraints.get("min_subquests", 1),
        }

        # ------------------------------------------------------------------
        # STEP 1: PLAN — Ask the LLM to create a plan
        # ------------------------------------------------------------------
        plan_prompt = PLAN_PROMPT.format(**fmt_base)
        plan_steps = None

        for attempt in range(CONFIG.json_repair_max_attempts):
            response = self.llm.generate(
                prompt=plan_prompt,
                system=SYSTEM_PROMPT,
                temperature=CONFIG.structured_temperature,
            )
            llm_calls += 1
            total_tokens += response.prompt_tokens + response.completion_tokens

            tracer.log(
                step_type="llm_call",
                prompt=plan_prompt[:500] + "..." if len(plan_prompt) > 500 else plan_prompt,
                response=response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
                duration_ms=response.duration_ms,
                tokens_estimate={"input": response.prompt_tokens, "output": response.completion_tokens},
                metadata={"phase": "plan", "attempt": attempt + 1},
            )

            if not response.success:
                tracer.log(step_type="error", metadata={"error": response.error, "phase": "plan"})
                continue

            parsed = extract_json(response.text)
            if parsed is not None and isinstance(parsed, dict) and "steps" in parsed:
                plan_steps = parsed["steps"]
                if isinstance(plan_steps, list) and len(plan_steps) > 0:
                    tracer.log(
                        step_type="parse",
                        parsed_json=parsed,
                        parse_success=True,
                        metadata={"phase": "plan", "num_steps": len(plan_steps)},
                    )
                    break
                else:
                    plan_steps = None

            tracer.log(
                step_type="repair",
                response=response.text[:500],
                parse_success=False,
                metadata={"phase": "plan", "attempt": attempt + 1},
            )
            plan_prompt = (
                f"Your previous response was not valid JSON. "
                f"Please try again. Respond with ONLY a JSON object.\n\n{plan_prompt}"
            )

        # Fallback plan if LLM failed to produce one
        if not plan_steps:
            tracer.log(
                step_type="error",
                metadata={"phase": "plan", "error": "Failed to generate plan, using fallback"},
            )
            plan_steps = [
                "Define the quest theme, title, description, and 3-act storyline",
                "Create 3-5 quest objectives with types and locations",
                "Design enemy encounters with stats appropriate to difficulty",
                "Create sub-quests that connect to the main storyline",
                "Write NPC dialog trees with player choices",
                "Define rewards appropriate to the quest difficulty",
                "Design environmental puzzles that fit the theme",
                "Create lore items, dynamic events, and branching consequences",
            ]

        # Truncate or pad to max_steps
        plan_steps = plan_steps[:CONFIG.plan_max_steps]

        tracer.log(
            step_type="decision",
            metadata={
                "phase": "plan_finalized",
                "plan_steps": plan_steps,
                "num_steps": len(plan_steps),
            },
        )

        # ------------------------------------------------------------------
        # STEP 2: EXECUTE — Run each plan step
        # ------------------------------------------------------------------
        step_results = []  # List of (step_description, parsed_json) tuples
        plan_text = self._format_plan(plan_steps)

        step_index = 0
        while step_index < len(plan_steps):
            step_desc = plan_steps[step_index]
            step_number = step_index + 1

            tracer.log(
                step_type="decision",
                metadata={
                    "phase": "execute",
                    "step_number": step_number,
                    "step_description": step_desc,
                },
            )

            # Classify what component this step is about
            component = self._classify_step(step_desc)

            # Build the execution prompt
            prior_results = self._format_prior_results(step_results)
            exec_prompt = self._build_execute_prompt(
                component=component,
                step_number=step_number,
                step_description=step_desc,
                plan_text=plan_text,
                prior_results=prior_results,
                fmt_base=fmt_base,
            )

            # Call LLM with repair loop
            parsed = None
            for attempt in range(CONFIG.json_repair_max_attempts):
                response = self.llm.generate(
                    prompt=exec_prompt,
                    system=SYSTEM_PROMPT,
                    temperature=CONFIG.default_temperature,
                )
                llm_calls += 1
                total_tokens += response.prompt_tokens + response.completion_tokens

                tracer.log(
                    step_type="llm_call",
                    prompt=exec_prompt[:500] + "..." if len(exec_prompt) > 500 else exec_prompt,
                    response=response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
                    duration_ms=response.duration_ms,
                    tokens_estimate={"input": response.prompt_tokens, "output": response.completion_tokens},
                    metadata={
                        "phase": "execute",
                        "step_number": step_number,
                        "component": component,
                        "attempt": attempt + 1,
                    },
                )

                if not response.success:
                    tracer.log(
                        step_type="error",
                        metadata={"error": response.error, "step_number": step_number},
                    )
                    continue

                parsed = extract_json(response.text)
                if parsed is not None:
                    tracer.log(
                        step_type="parse",
                        parsed_json=parsed,
                        parse_success=True,
                        metadata={"step_number": step_number, "component": component},
                    )
                    break
                else:
                    tracer.log(
                        step_type="repair",
                        response=response.text[:500],
                        parse_success=False,
                        metadata={"step_number": step_number, "attempt": attempt + 1},
                    )
                    exec_prompt = (
                        f"Your previous response was not valid JSON. "
                        f"Please try again. Respond with ONLY a JSON object.\n\n{exec_prompt}"
                    )

            if parsed is not None:
                step_results.append((step_desc, parsed))
                tracer.log(
                    step_type="decision",
                    metadata={
                        "phase": "execute_complete",
                        "step_number": step_number,
                        "component": component,
                        "success": True,
                    },
                )
                step_index += 1
            else:
                # ----------------------------------------------------------
                # STEP 3: REPLAN — Step failed, attempt replan if allowed
                # ----------------------------------------------------------
                tracer.log(
                    step_type="error",
                    metadata={
                        "phase": "execute_failed",
                        "step_number": step_number,
                        "step_description": step_desc,
                    },
                )

                if replans_used < CONFIG.plan_max_replans:
                    replans_used += 1
                    remaining = len(plan_steps) - step_index
                    new_plan_steps = self._replan(
                        task=task,
                        step_results=step_results,
                        failed_step_number=step_number,
                        failed_step_description=step_desc,
                        remaining_steps=remaining,
                        fmt_base=fmt_base,
                        tracer=tracer,
                    )
                    if new_plan_steps:
                        llm_calls += 1  # replan call counted
                        total_tokens += 0  # tokens tracked inside _replan via tracer
                        # Replace remaining plan steps with new ones
                        plan_steps = plan_steps[:step_index] + new_plan_steps
                        plan_text = self._format_plan(plan_steps)
                        tracer.log(
                            step_type="decision",
                            metadata={
                                "phase": "replan_complete",
                                "replans_used": replans_used,
                                "new_remaining_steps": new_plan_steps,
                            },
                        )
                        # Don't increment step_index — retry from same position
                        # with new step description
                        continue
                    else:
                        tracer.log(
                            step_type="error",
                            metadata={"phase": "replan_failed", "replans_used": replans_used},
                        )
                        step_index += 1  # Skip this step
                else:
                    tracer.log(
                        step_type="error",
                        metadata={
                            "phase": "replan_exhausted",
                            "replans_used": replans_used,
                            "max_replans": CONFIG.plan_max_replans,
                        },
                    )
                    step_index += 1  # Skip this step

        # ------------------------------------------------------------------
        # SYNTHESIS — Assemble all step results into a final quest
        # ------------------------------------------------------------------
        quest = self._synthesize(
            task=task,
            quest_id=quest_id,
            step_results=step_results,
            fmt_base=fmt_base,
            tracer=tracer,
        )

        if quest is not None:
            # Track tokens from synthesis call
            llm_calls += 1
        else:
            # Synthesis failed — build quest directly from step results
            tracer.log(
                step_type="error",
                metadata={"phase": "synthesis_failed", "error": "Building quest from raw step results"},
            )
            quest = self._build_quest_from_steps(
                task=task,
                quest_id=quest_id,
                step_results=step_results,
            )

        # Finalize metadata
        duration = time.time() - start_time
        quest.generated_by = self.pattern_name
        quest.generation_trace_id = tracer.trace_id
        quest.generation_duration_seconds = duration
        quest.llm_calls_count = llm_calls
        quest.total_tokens_estimate = total_tokens

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
        """Adapt a quest using the Plan & Execute pattern.

        Creates a 2-3 step adaptation plan, then executes each step.
        Faster than full generation — uses a miniature plan/execute cycle.
        """
        quest = adaptation_task.current_quest
        event_type = adaptation_task.event_type
        event_details = adaptation_task.event_details
        game_state = adaptation_task.game_state
        zones = ", ".join(CONFIG.world_zones)

        quest_summary = self._build_quest_summary_for_adapt(quest)
        game_state_str = self._format_game_state_for_adapt(game_state)

        # --- Step 1: PLAN the adaptation ---
        plan_prompt = (
            f"You need to adapt a quest based on a game event. "
            f"Create a short plan (2-3 steps) for how to modify the quest.\n\n"
            f"QUEST SUMMARY:\n{quest_summary}\n\n"
            f"GAME STATE:\n{game_state_str}\n\n"
            f"EVENT: {event_type}\n"
            f"EVENT DETAILS: {json.dumps(event_details)}\n\n"
            f"Create a plan as a JSON object:\n"
            f'{{"steps": ["step 1 description", "step 2 description", "step 3 description"]}}\n\n'
            f"Keep the plan to 2-3 concrete steps.\n"
            f"Respond with ONLY the JSON object."
        )

        plan_steps = None
        current_prompt = plan_prompt
        for attempt in range(CONFIG.json_repair_max_attempts):
            response = self.llm.generate(
                prompt=current_prompt,
                system=SYSTEM_PROMPT,
                temperature=CONFIG.structured_temperature,
            )
            if not response.success:
                continue
            parsed = extract_json(response.text)
            if parsed and isinstance(parsed, dict) and "steps" in parsed:
                steps = parsed["steps"]
                if isinstance(steps, list) and len(steps) > 0:
                    plan_steps = steps[:3]  # Max 3 steps
                    break
            current_prompt = (
                "Your previous response was not valid JSON. "
                "Please try again. Respond with ONLY a JSON object.\n\n"
                + plan_prompt
            )

        if not plan_steps:
            plan_steps = [
                f"Analyze the impact of {event_type} on the quest",
                "Determine what objectives/enemies/narrative need to change",
                "Generate the modification",
            ]

        # --- Step 2: EXECUTE — generate modification following the plan ---
        plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan_steps))

        execute_prompt = (
            f"Execute this adaptation plan for a quest:\n\n"
            f"PLAN:\n{plan_text}\n\n"
            f"QUEST SUMMARY:\n{quest_summary}\n\n"
            f"GAME STATE:\n{game_state_str}\n\n"
            f"EVENT: {event_type}\n"
            f"EVENT DETAILS: {json.dumps(event_details)}\n\n"
            f"Valid zones: {zones}\n\n"
            f"Follow your plan and generate a quest modification as a JSON object:\n"
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

        mod_dict = None
        current_prompt = execute_prompt
        for attempt in range(CONFIG.json_repair_max_attempts):
            response = self.llm.generate(
                prompt=current_prompt,
                system=SYSTEM_PROMPT,
                temperature=CONFIG.default_temperature,
            )
            if not response.success:
                continue
            parsed = extract_json(response.text)
            if parsed and isinstance(parsed, dict):
                mod_dict = parsed
                break
            current_prompt = (
                "Your previous response was not valid JSON. "
                "Please try again. Respond with ONLY a JSON object.\n\n"
                + execute_prompt
            )

        if mod_dict is None:
            return QuestModification(
                narrative_update=f"The winds of fate shift as {event_type.replace('_', ' ')} occurs...",
                reason=f"Plan & Execute adaptation fallback for {event_type}",
            )

        return QuestModification(
            modified_objectives=mod_dict.get("modified_objectives", []),
            added_objectives=mod_dict.get("added_objectives", []),
            removed_objective_ids=mod_dict.get("removed_objective_ids", []),
            added_enemies=mod_dict.get("added_enemies", []),
            removed_enemy_ids=mod_dict.get("removed_enemy_ids", []),
            added_dialogs=mod_dict.get("added_dialogs", []),
            narrative_update=mod_dict.get("narrative_update", ""),
            reason=mod_dict.get("reason", f"Plan & Execute adaptation for {event_type}"),
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

    # ------------------------------------------------------------------
    # Planning helpers
    # ------------------------------------------------------------------

    def _format_plan(self, plan_steps: list[str]) -> str:
        """Format plan steps as numbered text for inclusion in prompts."""
        lines = []
        for i, step in enumerate(plan_steps, 1):
            lines.append(f"  {i}. {step}")
        return "\n".join(lines)

    def _format_prior_results(self, step_results: list[tuple]) -> str:
        """Format prior step results as text for inclusion in prompts."""
        if not step_results:
            return "No prior results yet. This is the first step."
        lines = []
        for i, (desc, result) in enumerate(step_results, 1):
            result_str = json.dumps(result, indent=2)
            # Truncate very long results to keep prompt manageable
            if len(result_str) > 1500:
                result_str = result_str[:1500] + "\n  ... (truncated)"
            lines.append(f"Step {i} ({desc}):\n{result_str}")
        return "\n\n".join(lines)

    def _classify_step(self, step_description: str) -> str:
        """Classify a plan step description into a known component type.

        Uses keyword matching to determine which prompt template to use.
        Returns the component name or 'generic' if no match is found.
        """
        desc_lower = step_description.lower()
        best_match = "generic"
        best_score = 0

        for component, keywords in COMPONENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in desc_lower)
            if score > best_score:
                best_score = score
                best_match = component

        return best_match

    def _build_execute_prompt(
        self,
        component: str,
        step_number: int,
        step_description: str,
        plan_text: str,
        prior_results: str,
        fmt_base: dict,
    ) -> str:
        """Build the execution prompt for a specific plan step."""
        templates = {
            "storyline": EXECUTE_STEP_STORYLINE,
            "objectives": EXECUTE_STEP_OBJECTIVES,
            "enemies": EXECUTE_STEP_ENEMIES,
            "subquests": EXECUTE_STEP_SUBQUESTS,
            "dialogs": EXECUTE_STEP_DIALOGS,
            "rewards": EXECUTE_STEP_REWARDS,
            "puzzles": EXECUTE_STEP_PUZZLES,
            "lore_and_events": EXECUTE_STEP_LORE_AND_EVENTS,
            "generic": EXECUTE_STEP_GENERIC,
        }

        template = templates.get(component, EXECUTE_STEP_GENERIC)

        fmt = {
            **fmt_base,
            "step_number": step_number,
            "step_description": step_description,
            "plan_text": plan_text,
            "prior_results": prior_results,
        }

        return template.format(**fmt)

    def _replan(
        self,
        task: GenerationTask,
        step_results: list[tuple],
        failed_step_number: int,
        failed_step_description: str,
        remaining_steps: int,
        fmt_base: dict,
        tracer: TraceLogger,
    ) -> list[str] | None:
        """Create a new plan for remaining steps after a failure."""
        completed_results = self._format_prior_results(step_results)

        replan_prompt = REPLAN_PROMPT.format(
            description=task.description,
            theme=task.theme,
            difficulty=task.difficulty,
            completed_results=completed_results,
            failed_step_number=failed_step_number,
            failed_step_description=failed_step_description,
            remaining_steps=remaining_steps,
        )

        for attempt in range(CONFIG.json_repair_max_attempts):
            response = self.llm.generate(
                prompt=replan_prompt,
                system=SYSTEM_PROMPT,
                temperature=CONFIG.structured_temperature,
            )

            tracer.log(
                step_type="llm_call",
                prompt=replan_prompt[:500] + "..." if len(replan_prompt) > 500 else replan_prompt,
                response=response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
                duration_ms=response.duration_ms,
                tokens_estimate={"input": response.prompt_tokens, "output": response.completion_tokens},
                metadata={"phase": "replan", "attempt": attempt + 1},
            )

            if not response.success:
                continue

            parsed = extract_json(response.text)
            if parsed and isinstance(parsed, dict) and "steps" in parsed:
                new_steps = parsed["steps"]
                if isinstance(new_steps, list) and len(new_steps) > 0:
                    tracer.log(
                        step_type="parse",
                        parsed_json=parsed,
                        parse_success=True,
                        metadata={"phase": "replan", "new_steps": len(new_steps)},
                    )
                    return new_steps

            replan_prompt = (
                f"Your previous response was not valid JSON. "
                f"Please try again. Respond with ONLY a JSON object.\n\n{replan_prompt}"
            )

        return None

    # ------------------------------------------------------------------
    # Synthesis — assemble final quest from step results
    # ------------------------------------------------------------------

    def _synthesize(
        self,
        task: GenerationTask,
        quest_id: str,
        step_results: list[tuple],
        fmt_base: dict,
        tracer: TraceLogger,
    ) -> QuestData | None:
        """Use the LLM to synthesize all step results into a final quest."""
        all_results = self._format_prior_results(step_results)

        synth_prompt = SYNTHESIS_PROMPT.format(
            **fmt_base,
            all_results=all_results,
        )

        for attempt in range(CONFIG.json_repair_max_attempts):
            response = self.llm.generate(
                prompt=synth_prompt,
                system=SYSTEM_PROMPT,
                temperature=CONFIG.structured_temperature,
            )

            tracer.log(
                step_type="llm_call",
                prompt=synth_prompt[:500] + "..." if len(synth_prompt) > 500 else synth_prompt,
                response=response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
                duration_ms=response.duration_ms,
                tokens_estimate={"input": response.prompt_tokens, "output": response.completion_tokens},
                metadata={"phase": "synthesis", "attempt": attempt + 1},
            )

            if not response.success:
                continue

            parsed = extract_json(response.text)
            if parsed and isinstance(parsed, dict):
                tracer.log(
                    step_type="parse",
                    parsed_json=parsed,
                    parse_success=True,
                    metadata={"phase": "synthesis"},
                )
                return self._parsed_to_quest(parsed, quest_id, task)

            tracer.log(
                step_type="repair",
                response=response.text[:500],
                parse_success=False,
                metadata={"phase": "synthesis", "attempt": attempt + 1},
            )
            synth_prompt = (
                f"Your previous response was not valid JSON. "
                f"Please try again. Respond with ONLY a JSON object.\n\n{synth_prompt}"
            )

        return None

    def _parsed_to_quest(self, parsed: dict, quest_id: str, task: GenerationTask) -> QuestData:
        """Convert a fully-parsed synthesis dict into a QuestData."""
        return QuestData(
            id=quest_id,
            title=parsed.get("title", "Untitled Quest"),
            description=parsed.get("description", ""),
            theme=task.theme,
            difficulty=task.difficulty,
            storyline=parsed.get("storyline", []),
            objectives=self._parse_objectives(parsed.get("objectives", [])),
            enemies=self._parse_enemies(parsed.get("enemies", [])),
            sub_quests=self._parse_subquests(parsed.get("sub_quests", []), quest_id),
            npc_dialogs=self._parse_dialogs(parsed.get("npc_dialogs", [])),
            rewards=self._parse_rewards(parsed.get("rewards", [])),
            puzzles=self._parse_puzzles(parsed.get("puzzles", [])),
            lore_items=self._parse_lore(parsed.get("lore_items", [])),
            dynamic_events=self._parse_events(parsed.get("dynamic_events", [])),
            branching_consequences=self._parse_branches(parsed.get("branching_consequences", [])),
        )

    def _build_quest_from_steps(
        self,
        task: GenerationTask,
        quest_id: str,
        step_results: list[tuple],
    ) -> QuestData:
        """Fallback: build QuestData directly from individual step results
        when the synthesis LLM call fails.
        """
        title = "Untitled Quest"
        description = ""
        storyline = []
        objectives_raw = []
        enemies_raw = []
        sub_quests_raw = []
        npc_dialogs_raw = []
        rewards_raw = []
        puzzles_raw = []
        lore_items_raw = []
        dynamic_events_raw = []
        branching_consequences_raw = []

        for _desc, result in step_results:
            if not isinstance(result, dict):
                continue

            component = result.get("component", "")

            # Storyline data
            if "title" in result and "storyline" in result:
                title = result.get("title", title)
                description = result.get("description", description)
                storyline = result.get("storyline", storyline)
            elif component == "storyline":
                title = result.get("title", title)
                description = result.get("description", description)
                storyline = result.get("storyline", storyline)

            # Objectives
            if "objectives" in result and component in ("objectives", ""):
                objectives_raw.extend(result["objectives"])

            # Enemies
            if "enemies" in result:
                enemies_raw.extend(result["enemies"])

            # Sub-quests
            if "sub_quests" in result:
                sub_quests_raw.extend(result["sub_quests"])

            # Dialogs
            if "npc_dialogs" in result:
                npc_dialogs_raw.extend(result["npc_dialogs"])

            # Rewards
            if "rewards" in result and component in ("rewards", ""):
                rewards_raw.extend(result["rewards"])

            # Puzzles
            if "puzzles" in result:
                puzzles_raw.extend(result["puzzles"])

            # Lore and events
            if "lore_items" in result:
                lore_items_raw.extend(result["lore_items"])
            if "dynamic_events" in result:
                dynamic_events_raw.extend(result["dynamic_events"])
            if "branching_consequences" in result:
                branching_consequences_raw.extend(result["branching_consequences"])

        return QuestData(
            id=quest_id,
            title=title,
            description=description,
            theme=task.theme,
            difficulty=task.difficulty,
            storyline=storyline,
            objectives=self._parse_objectives(objectives_raw),
            enemies=self._parse_enemies(enemies_raw),
            sub_quests=self._parse_subquests(sub_quests_raw, quest_id),
            npc_dialogs=self._parse_dialogs(npc_dialogs_raw),
            rewards=self._parse_rewards(rewards_raw),
            puzzles=self._parse_puzzles(puzzles_raw),
            lore_items=self._parse_lore(lore_items_raw),
            dynamic_events=self._parse_events(dynamic_events_raw),
            branching_consequences=self._parse_branches(branching_consequences_raw),
        )

    # ------------------------------------------------------------------
    # Parsing helpers — convert raw dicts to dataclass instances
    # ------------------------------------------------------------------

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
