"""Tree of Thought (ToT) pattern for quest generation.

For each quest component, generates B=3 candidate solutions, scores
each with a concrete rubric, and selects the best. This is the most
LLM-call-intensive pattern (~30+ calls per quest).
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
from .prompts.tot_prompts import (
    SYSTEM_PROMPT, SCORING_SYSTEM_PROMPT,
    COMPONENT_ORDER, COMPONENT_PROMPTS, SCORING_PROMPTS,
)


class TreeOfThoughtPattern(AgenticPattern):
    """Tree of Thought pattern: Branch → Score → Select for each component.

    For each quest component:
    1. Generate B candidates (CONFIG.tot_branching, default 3)
    2. Score each candidate with a rubric-based scoring prompt
    3. Select the highest-scoring candidate
    """

    @property
    def pattern_name(self) -> str:
        return "tot"

    def generate(self, task: GenerationTask, world_state: WorldState = None) -> QuestData:
        """Generate a complete quest using Tree of Thought branching."""
        tracer = self._create_tracer(task)
        start_time = time.time()
        quest_id = f"quest_{uuid.uuid4().hex[:8]}"
        llm_calls = 0
        total_tokens = 0
        branching_factor = CONFIG.tot_branching

        # Scratchpad accumulates the best candidate for each component
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
                    "thought": f"ToT: generating {branching_factor} candidates for {component}, will score and select best.",
                },
            )

            # Build the base prompt for this component
            base_prompt = self._build_component_prompt(component, scratchpad, task)

            # --- Branch: generate B candidates ---
            candidates = []
            for branch_idx in range(branching_factor):
                parsed = None
                prompt = base_prompt

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
                        metadata={"component": component, "branch": branch_idx + 1, "attempt": attempt + 1},
                    )

                    if not response.success:
                        tracer.log(step_type="error", metadata={"error": response.error, "component": component, "branch": branch_idx + 1})
                        continue

                    parsed = extract_json(response.text)
                    if parsed is not None:
                        tracer.log(
                            step_type="parse",
                            parsed_json=parsed,
                            parse_success=True,
                            metadata={"component": component, "branch": branch_idx + 1},
                        )
                        break
                    else:
                        tracer.log(
                            step_type="repair",
                            response=response.text[:500],
                            parse_success=False,
                            metadata={"component": component, "branch": branch_idx + 1, "attempt": attempt + 1},
                        )
                        prompt = (
                            f"Your previous response was not valid JSON. "
                            f"Please try again. Respond with ONLY a JSON object.\n\n{base_prompt}"
                        )

                if parsed is not None:
                    candidates.append(parsed)

            if not candidates:
                tracer.log(
                    step_type="error",
                    metadata={"component": component, "error": "No valid candidates generated across all branches"},
                )
                continue

            # --- Score each candidate ---
            scored_candidates = []
            for cand_idx, candidate in enumerate(candidates):
                score = self._score_candidate(
                    component, candidate, scratchpad, task, tracer,
                )
                llm_calls += 1  # scoring call
                total_tokens += 0  # tokens tracked inside _score_candidate via tracer
                scored_candidates.append((score, cand_idx, candidate))

                tracer.log(
                    step_type="decision",
                    metadata={
                        "component": component,
                        "branch": cand_idx + 1,
                        "score": score,
                        "thought": f"Candidate {cand_idx + 1} scored {score:.2f}",
                    },
                )

            # --- Select best candidate ---
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_idx, best_candidate = scored_candidates[0]

            tracer.log(
                step_type="decision",
                metadata={
                    "component": component,
                    "selected_branch": best_idx + 1,
                    "best_score": best_score,
                    "all_scores": [s for s, _, _ in scored_candidates],
                    "thought": f"Selected candidate {best_idx + 1} with score {best_score:.2f}",
                },
            )

            # Integrate best candidate into scratchpad
            self._integrate_component(component, best_candidate, scratchpad)

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
        """Adapt a quest using a simplified Tree of Thought approach.

        Generates 2 candidate modifications, scores each, and picks the best.
        This is a faster version of the full ToT pattern (2 branches instead of 3).
        """
        quest = adaptation_task.current_quest
        event_type = adaptation_task.event_type
        event_details = adaptation_task.event_details
        game_state = adaptation_task.game_state
        zones = ", ".join(CONFIG.world_zones)

        quest_summary = self._build_quest_summary_for_adapt(quest)
        game_state_str = self._format_game_state_for_adapt(game_state)

        # Base prompt for generating candidates
        base_prompt = (
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
            f"Be creative and make the modification feel natural for the story.\n"
            f"Respond with ONLY the JSON object."
        )

        # --- Generate 2 candidates ---
        candidates = []
        for branch_idx in range(2):
            parsed = None
            prompt = base_prompt
            for attempt in range(CONFIG.json_repair_max_attempts):
                response = self.llm.generate(
                    prompt=prompt,
                    system=SYSTEM_PROMPT,
                    temperature=CONFIG.default_temperature,
                )
                if not response.success:
                    continue
                parsed = extract_json(response.text)
                if parsed and isinstance(parsed, dict):
                    break
                prompt = (
                    "Your previous response was not valid JSON. "
                    "Please try again. Respond with ONLY a JSON object.\n\n"
                    + base_prompt
                )
            if parsed:
                candidates.append(parsed)

        if not candidates:
            return QuestModification(
                narrative_update=f"The winds of fate shift as {event_type.replace('_', ' ')} occurs...",
                reason=f"ToT adaptation fallback for {event_type}",
            )

        if len(candidates) == 1:
            return self._dict_to_modification(candidates[0], event_type)

        # --- Score each candidate ---
        scoring_prompt_template = (
            f"Score this quest modification on a scale of 0.0 to 1.0.\n\n"
            f"EVENT: {event_type}\n"
            f"QUEST: {quest.title} (difficulty: {quest.difficulty})\n\n"
            f"MODIFICATION:\n{{candidate_json}}\n\n"
            f"Score based on:\n"
            f"- Narrative quality (does the story beat make sense?)\n"
            f"- Balance (are new enemies/objectives appropriate?)\n"
            f"- Relevance (does it relate to the triggering event?)\n"
            f"- Creativity (is it interesting for the player?)\n\n"
            f"Respond with a JSON object: "
            f'{{"total_score": 0.75, "reasoning": "brief explanation"}}'
        )

        scored = []
        for idx, candidate in enumerate(candidates):
            scoring_prompt = scoring_prompt_template.replace(
                "{candidate_json}",
                json.dumps(candidate, indent=2)[:1500],
            )
            response = self.llm.generate(
                prompt=scoring_prompt,
                system=SCORING_SYSTEM_PROMPT,
                temperature=CONFIG.structured_temperature,
            )
            score = 0.5  # default
            if response.success:
                score_parsed = extract_json(response.text)
                if score_parsed and isinstance(score_parsed, dict):
                    try:
                        score = float(score_parsed.get("total_score", 0.5))
                        score = max(0.0, min(1.0, score))
                    except (TypeError, ValueError):
                        score = 0.5
            scored.append((score, candidate))

        # Pick best
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        return self._dict_to_modification(best, event_type)

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
            reason=d.get("reason", f"ToT adaptation for {event_type}"),
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
    # Scoring
    # ------------------------------------------------------------------

    def _score_candidate(
        self,
        component: str,
        candidate: dict,
        scratchpad: dict,
        task: GenerationTask,
        tracer: TraceLogger,
    ) -> float:
        """Score a single candidate using the component's rubric prompt.

        Returns a float 0.0-1.0. On parse failure, returns 0.0.
        """
        scoring_template = SCORING_PROMPTS[component]
        zones = ", ".join(CONFIG.world_zones)

        # Build format kwargs based on component type
        fmt = {
            "title": scratchpad.get("title", ""),
            "theme": task.theme,
            "difficulty": task.difficulty,
            "description": task.description,
            "storyline": "\n".join(scratchpad.get("storyline", [])),
            "objectives": self._summarize_objectives(scratchpad.get("objectives", [])),
            "enemies": self._summarize_enemies(scratchpad.get("enemies", [])),
            "zones": zones,
            "min_subquests": task.constraints.get("min_subquests", 1),
            "candidate_json": json.dumps(candidate, indent=2)[:2000],
        }

        # Storyline-specific fields
        if component == "storyline":
            fmt["candidate_title"] = candidate.get("title", "")
            fmt["candidate_description"] = candidate.get("description", "")
            fmt["candidate_storyline"] = json.dumps(candidate.get("storyline", []))

        scoring_prompt = scoring_template.format(**fmt)

        response = self.llm.generate(
            prompt=scoring_prompt,
            system=SCORING_SYSTEM_PROMPT,
            temperature=CONFIG.structured_temperature,
        )

        tracer.log(
            step_type="llm_call",
            prompt=scoring_prompt[:500] + "..." if len(scoring_prompt) > 500 else scoring_prompt,
            response=response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
            duration_ms=response.duration_ms,
            tokens_estimate={"input": response.prompt_tokens, "output": response.completion_tokens},
            metadata={"component": component, "action": "scoring"},
        )

        if not response.success:
            tracer.log(step_type="error", metadata={"error": response.error, "component": component, "action": "scoring"})
            return 0.0

        parsed = extract_json(response.text)
        if parsed is None:
            tracer.log(
                step_type="repair",
                response=response.text[:500],
                parse_success=False,
                metadata={"component": component, "action": "scoring_parse_fail"},
            )
            return 0.0

        # Extract total_score, clamp to [0.0, 1.0]
        try:
            score = float(parsed.get("total_score", 0.0))
            score = max(0.0, min(1.0, score))
        except (TypeError, ValueError):
            score = 0.0

        return score

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_component_prompt(self, component: str, scratchpad: dict, task: GenerationTask) -> str:
        """Build the generation prompt for a specific component."""
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
