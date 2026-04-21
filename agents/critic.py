"""Critic pattern for quest generation.

Separate generator and critic personas. For each quest component:
1. Generator produces a component
2. Critic evaluates against explicit checklist (thematic consistency,
   difficulty balance, narrative coherence, completeness)
3. If critic finds issues, generator revises (up to CONFIG.critic_max_rounds)

Key difference from Reflection: Critic is GRANULAR (per-component adversarial
review), Reflection is HOLISTIC (whole quest post-hoc review).
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
from .prompts.critic_prompts import (
    GENERATOR_SYSTEM_PROMPT, CRITIC_SYSTEM_PROMPT,
    COMPONENT_ORDER, COMPONENT_PROMPTS, CRITIC_PROMPTS,
    REVISION_PROMPT,
)


class CriticPattern(AgenticPattern):
    """Critic pattern: Generator produces, Critic reviews, Generator revises.

    For each component, the generator and critic engage in an adversarial
    loop (up to critic_max_rounds) until the critic approves or rounds
    are exhausted.
    """

    @property
    def pattern_name(self) -> str:
        return "critic"

    def generate(self, task: GenerationTask, world_state: WorldState = None) -> QuestData:
        """Generate a complete quest using the Generator-Critic loop."""
        tracer = self._create_tracer(task)
        start_time = time.time()
        quest_id = f"quest_{uuid.uuid4().hex[:8]}"
        llm_calls = 0
        total_tokens = 0
        max_rounds = CONFIG.critic_max_rounds

        # Scratchpad accumulates the approved components
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
                metadata={
                    "component": component,
                    "thought": f"Critic pattern: generating {component}, then critic review (max {max_rounds} rounds).",
                },
            )

            # --- Initial generation ---
            gen_prompt = self._build_component_prompt(component, scratchpad, task)
            current_parsed = None

            for attempt in range(CONFIG.json_repair_max_attempts):
                response = self.llm.generate(
                    prompt=gen_prompt,
                    system=GENERATOR_SYSTEM_PROMPT,
                    temperature=CONFIG.default_temperature,
                )
                llm_calls += 1
                total_tokens += response.prompt_tokens + response.completion_tokens

                tracer.log(
                    step_type="llm_call",
                    prompt=gen_prompt[:500] + "..." if len(gen_prompt) > 500 else gen_prompt,
                    response=response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
                    duration_ms=response.duration_ms,
                    tokens_estimate={"input": response.prompt_tokens, "output": response.completion_tokens},
                    metadata={"component": component, "role": "generator", "attempt": attempt + 1},
                )

                if not response.success:
                    tracer.log(step_type="error", metadata={"error": response.error, "component": component, "role": "generator"})
                    continue

                current_parsed = extract_json(response.text)
                if current_parsed is not None:
                    tracer.log(
                        step_type="parse",
                        parsed_json=current_parsed,
                        parse_success=True,
                        metadata={"component": component, "role": "generator"},
                    )
                    break
                else:
                    tracer.log(
                        step_type="repair",
                        response=response.text[:500],
                        parse_success=False,
                        metadata={"component": component, "role": "generator", "attempt": attempt + 1},
                    )
                    gen_prompt = (
                        f"Your previous response was not valid JSON. "
                        f"Please try again. Respond with ONLY a JSON object.\n\n"
                        + self._build_component_prompt(component, scratchpad, task)
                    )

            if current_parsed is None:
                tracer.log(
                    step_type="error",
                    metadata={"component": component, "error": "Generator failed to produce valid JSON after all attempts"},
                )
                continue

            # --- Critic review loop ---
            approved = False
            for critic_round in range(max_rounds):
                tracer.log(
                    step_type="decision",
                    metadata={
                        "component": component,
                        "critic_round": critic_round + 1,
                        "thought": f"Sending {component} to critic for review (round {critic_round + 1}/{max_rounds}).",
                    },
                )

                # Build critic prompt
                critic_prompt = self._build_critic_prompt(component, current_parsed, scratchpad, task)
                critic_response = self.llm.generate(
                    prompt=critic_prompt,
                    system=CRITIC_SYSTEM_PROMPT,
                    temperature=CONFIG.structured_temperature,
                )
                llm_calls += 1
                total_tokens += critic_response.prompt_tokens + critic_response.completion_tokens

                tracer.log(
                    step_type="llm_call",
                    prompt=critic_prompt[:500] + "..." if len(critic_prompt) > 500 else critic_prompt,
                    response=critic_response.text[:1000] + "..." if len(critic_response.text) > 1000 else critic_response.text,
                    duration_ms=critic_response.duration_ms,
                    tokens_estimate={"input": critic_response.prompt_tokens, "output": critic_response.completion_tokens},
                    metadata={"component": component, "role": "critic", "round": critic_round + 1},
                )

                if not critic_response.success:
                    tracer.log(step_type="error", metadata={"error": critic_response.error, "component": component, "role": "critic"})
                    # If critic fails, accept what we have
                    approved = True
                    break

                critic_parsed = extract_json(critic_response.text)
                if critic_parsed is None:
                    tracer.log(
                        step_type="repair",
                        response=critic_response.text[:500],
                        parse_success=False,
                        metadata={"component": component, "role": "critic", "round": critic_round + 1},
                    )
                    # If we cannot parse critic output, accept what we have
                    approved = True
                    break

                tracer.log(
                    step_type="parse",
                    parsed_json=critic_parsed,
                    parse_success=True,
                    metadata={"component": component, "role": "critic", "round": critic_round + 1},
                )

                # Check if critic approved
                is_approved = critic_parsed.get("approved", False)
                issues = critic_parsed.get("issues", [])
                revision_instructions = critic_parsed.get("revision_instructions", "")

                # Log checklist results
                checklist = critic_parsed.get("checklist", [])
                pass_count = sum(1 for item in checklist if item.get("result") == "pass")
                fail_count = sum(1 for item in checklist if item.get("result") == "fail")

                tracer.log(
                    step_type="decision",
                    metadata={
                        "component": component,
                        "critic_round": critic_round + 1,
                        "approved": is_approved,
                        "checklist_pass": pass_count,
                        "checklist_fail": fail_count,
                        "issues": issues,
                        "thought": f"Critic {'approved' if is_approved else 'rejected'} {component} "
                                   f"({pass_count} pass, {fail_count} fail).",
                    },
                )

                if is_approved or not issues:
                    approved = True
                    break

                # --- Revision: generator addresses critic's issues ---
                revision_prompt = self._build_revision_prompt(
                    component, current_parsed, critic_parsed, scratchpad, task,
                )

                revised_parsed = None
                for attempt in range(CONFIG.json_repair_max_attempts):
                    rev_response = self.llm.generate(
                        prompt=revision_prompt,
                        system=GENERATOR_SYSTEM_PROMPT,
                        temperature=CONFIG.default_temperature,
                    )
                    llm_calls += 1
                    total_tokens += rev_response.prompt_tokens + rev_response.completion_tokens

                    tracer.log(
                        step_type="llm_call",
                        prompt=revision_prompt[:500] + "..." if len(revision_prompt) > 500 else revision_prompt,
                        response=rev_response.text[:1000] + "..." if len(rev_response.text) > 1000 else rev_response.text,
                        duration_ms=rev_response.duration_ms,
                        tokens_estimate={"input": rev_response.prompt_tokens, "output": rev_response.completion_tokens},
                        metadata={
                            "component": component,
                            "role": "generator",
                            "action": "revision",
                            "round": critic_round + 1,
                            "attempt": attempt + 1,
                        },
                    )

                    if not rev_response.success:
                        tracer.log(step_type="error", metadata={"error": rev_response.error, "component": component, "action": "revision"})
                        continue

                    revised_parsed = extract_json(rev_response.text)
                    if revised_parsed is not None:
                        tracer.log(
                            step_type="parse",
                            parsed_json=revised_parsed,
                            parse_success=True,
                            metadata={"component": component, "action": "revision", "round": critic_round + 1},
                        )
                        break
                    else:
                        tracer.log(
                            step_type="repair",
                            response=rev_response.text[:500],
                            parse_success=False,
                            metadata={"component": component, "action": "revision", "round": critic_round + 1, "attempt": attempt + 1},
                        )
                        revision_prompt = (
                            f"Your previous response was not valid JSON. "
                            f"Please try again. Respond with ONLY a JSON object.\n\n{revision_prompt}"
                        )

                if revised_parsed is not None:
                    current_parsed = revised_parsed
                    tracer.log(
                        step_type="decision",
                        metadata={
                            "component": component,
                            "critic_round": critic_round + 1,
                            "thought": f"Generator revised {component}. Sending back to critic.",
                        },
                    )
                else:
                    tracer.log(
                        step_type="error",
                        metadata={
                            "component": component,
                            "critic_round": critic_round + 1,
                            "error": "Revision failed to produce valid JSON, keeping previous version.",
                        },
                    )
                    # Keep current_parsed as is; critic will re-evaluate
                    # or we'll exhaust rounds

            if not approved:
                tracer.log(
                    step_type="decision",
                    metadata={
                        "component": component,
                        "thought": f"Max critic rounds exhausted for {component}. Using best available version.",
                    },
                )

            # Integrate the final version into scratchpad
            self._integrate_component(component, current_parsed, scratchpad)

            tracer.log(
                step_type="decision",
                metadata={
                    "component": component,
                    "observation": f"Finalized {component} after critic review. Scratchpad updated.",
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

        stats = tracer.get_stats()
        tracer.log(step_type="decision", metadata={"final_stats": stats})

        return quest

    def adapt(self, adaptation_task: AdaptationTask) -> QuestModification:
        """Adapt a quest using the Critic pattern: Generate -> Critic review -> Revise.

        Uses a single generation, one critic review, and one revision (3 LLM calls)
        for low-latency adaptation.
        """
        quest = adaptation_task.current_quest
        event_type = adaptation_task.event_type
        event_details = adaptation_task.event_details
        game_state = adaptation_task.game_state
        zones = ", ".join(CONFIG.world_zones)

        quest_summary = self._build_quest_summary_for_adapt(quest)
        game_state_str = self._format_game_state_for_adapt(game_state)

        # --- Phase 1: GENERATOR produces modification ---
        gen_prompt = (
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

        gen_dict = None
        current_prompt = gen_prompt
        for attempt in range(CONFIG.json_repair_max_attempts):
            response = self.llm.generate(
                prompt=current_prompt,
                system=GENERATOR_SYSTEM_PROMPT,
                temperature=CONFIG.default_temperature,
            )
            if not response.success:
                continue
            gen_dict = extract_json(response.text)
            if gen_dict and isinstance(gen_dict, dict):
                break
            current_prompt = (
                "Your previous response was not valid JSON. "
                "Please try again. Respond with ONLY a JSON object.\n\n"
                + gen_prompt
            )

        if gen_dict is None:
            return QuestModification(
                narrative_update=f"The winds of fate shift as {event_type.replace('_', ' ')} occurs...",
                reason=f"Critic adaptation fallback for {event_type}",
            )

        # --- Phase 2: CRITIC reviews the modification ---
        gen_json_str = json.dumps(gen_dict, indent=2)
        critic_prompt = (
            f"Review this quest modification critically.\n\n"
            f"EVENT: {event_type}\n"
            f"QUEST: {quest.title} (difficulty: {quest.difficulty}, theme: {quest.theme})\n\n"
            f"PROPOSED MODIFICATION:\n{gen_json_str}\n\n"
            f"CHECKLIST:\n"
            f"1. Thematic consistency: Does the modification fit the quest theme?\n"
            f"2. Difficulty balance: Are enemy stats and objective counts appropriate?\n"
            f"3. Narrative coherence: Does the narrative_update make sense for the event?\n"
            f"4. Completeness: Are all required JSON fields present and valid?\n"
            f"5. Zone validity: Are all locations valid zones? ({zones})\n\n"
            f"Respond with a JSON object:\n"
            f'{{"approved": true/false, '
            f'"issues": ["issue1", "issue2"], '
            f'"revision_instructions": "What to fix if not approved."}}'
        )

        critic_dict = None
        response = self.llm.generate(
            prompt=critic_prompt,
            system=CRITIC_SYSTEM_PROMPT,
            temperature=CONFIG.structured_temperature,
        )
        if response.success:
            critic_dict = extract_json(response.text)

        # If critic approves or we can't parse critic output, use generator output
        if critic_dict is None or critic_dict.get("approved", True):
            return self._dict_to_modification(gen_dict, event_type)

        # --- Phase 3: GENERATOR revises based on critic feedback ---
        issues = critic_dict.get("issues", [])
        revision_instructions = critic_dict.get("revision_instructions", "")
        feedback = "\n".join(f"- {i}" for i in issues)
        if revision_instructions:
            feedback += f"\n\nInstructions: {revision_instructions}"

        revise_prompt = (
            f"Revise this quest modification based on critic feedback:\n\n"
            f"ORIGINAL MODIFICATION:\n{gen_json_str}\n\n"
            f"CRITIC FEEDBACK:\n{feedback}\n\n"
            f"EVENT: {event_type}\n"
            f"Valid zones: {zones}\n\n"
            f"Respond with the improved JSON modification object. Same format.\n"
            f"Respond with ONLY the JSON object."
        )

        revised_dict = None
        current_prompt = revise_prompt
        for attempt in range(CONFIG.json_repair_max_attempts):
            response = self.llm.generate(
                prompt=current_prompt,
                system=GENERATOR_SYSTEM_PROMPT,
                temperature=CONFIG.default_temperature,
            )
            if not response.success:
                continue
            revised_dict = extract_json(response.text)
            if revised_dict and isinstance(revised_dict, dict):
                break
            current_prompt = (
                "Your previous response was not valid JSON. "
                "Please try again. Respond with ONLY a JSON object.\n\n"
                + revise_prompt
            )

        if revised_dict is not None:
            return self._dict_to_modification(revised_dict, event_type)

        return self._dict_to_modification(gen_dict, event_type)

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
            reason=d.get("reason", f"Critic adaptation for {event_type}"),
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
    # Prompt building
    # ------------------------------------------------------------------

    def _build_component_prompt(self, component: str, scratchpad: dict, task: GenerationTask) -> str:
        """Build the generator prompt for a specific component."""
        template = COMPONENT_PROMPTS[component]
        zones = ", ".join(CONFIG.world_zones)

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

    def _build_critic_prompt(
        self,
        component: str,
        candidate: dict,
        scratchpad: dict,
        task: GenerationTask,
    ) -> str:
        """Build the critic evaluation prompt for a component."""
        template = CRITIC_PROMPTS[component]
        zones = ", ".join(CONFIG.world_zones)

        fmt = {
            "title": scratchpad.get("title", ""),
            "theme": task.theme,
            "difficulty": task.difficulty,
            "description": task.description,
            "required_elements": ", ".join(task.required_elements) if task.required_elements else "none",
            "constraints": str(task.constraints),
            "zones": zones,
            "storyline": "\n".join(scratchpad.get("storyline", [])),
            "objectives": self._summarize_objectives(scratchpad.get("objectives", [])),
            "enemies": self._summarize_enemies(scratchpad.get("enemies", [])),
            "min_subquests": task.constraints.get("min_subquests", 1),
            "candidate_json": json.dumps(candidate, indent=2)[:2000],
        }

        # Storyline-specific fields
        if component == "storyline":
            fmt["candidate_title"] = candidate.get("title", "")
            fmt["candidate_description"] = candidate.get("description", "")
            fmt["candidate_storyline"] = json.dumps(candidate.get("storyline", []))

        return template.format(**fmt)

    def _build_revision_prompt(
        self,
        component: str,
        current: dict,
        critic_result: dict,
        scratchpad: dict,
        task: GenerationTask,
    ) -> str:
        """Build the revision prompt incorporating critic feedback."""
        issues = critic_result.get("issues", [])
        revision_instructions = critic_result.get("revision_instructions", "")

        # Build a combined feedback string from checklist failures
        checklist = critic_result.get("checklist", [])
        failed_items = [
            f"- {item.get('item', '?')}: {item.get('reason', 'no reason given')}"
            for item in checklist
            if item.get("result") == "fail"
        ]
        critic_feedback = "\n".join(failed_items) if failed_items else revision_instructions

        issues_list = "\n".join(f"- {issue}" for issue in issues) if issues else "See critic feedback above."

        return REVISION_PROMPT.format(
            component=component,
            component_upper=component.upper(),
            title=scratchpad.get("title", ""),
            theme=task.theme,
            difficulty=task.difficulty,
            original_json=json.dumps(current, indent=2)[:2000],
            critic_feedback=critic_feedback,
            issues_list=issues_list,
        )

    # ------------------------------------------------------------------
    # Component integration
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Quest assembly
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Parsing helpers: convert raw dicts to dataclass instances
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

    # ------------------------------------------------------------------
    # Summarization helpers for building context in prompts
    # ------------------------------------------------------------------

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
