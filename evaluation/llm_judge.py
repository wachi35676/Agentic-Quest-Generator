"""LLM-as-judge evaluation for quest quality.

Uses a separate LLM call (same Ollama model) to evaluate quest quality
from the perspective of a veteran game designer. The judge does NOT
know which pattern generated the quest (blind evaluation).

Each metric is scored on a 1-5 scale with reasoning.
"""

import json

from llm.client import OllamaClient
from llm.parser import extract_json
from quests.schema import QuestData


JUDGE_SYSTEM_PROMPT = """You are a veteran game designer with 20+ years of experience designing RPG quests.
You are reviewing a quest design document for quality. Be critical but fair.

You must respond ONLY with valid JSON in the exact format requested. No other text."""


def _build_quest_summary(quest: QuestData) -> str:
    """Build a text summary of the quest for the judge to evaluate.

    Deliberately omits the generated_by field so the evaluation is blind.
    """
    lines = []
    lines.append(f"QUEST: {quest.title}")
    lines.append(f"Theme: {quest.theme} | Difficulty: {quest.difficulty}")
    lines.append(f"\nDescription: {quest.description}")

    if quest.storyline:
        lines.append("\nStoryline:")
        for i, beat in enumerate(quest.storyline, 1):
            lines.append(f"  {i}. {beat}")

    if quest.objectives:
        lines.append(f"\nObjectives ({len(quest.objectives)}):")
        for obj in quest.objectives:
            optional = " [optional]" if obj.is_optional else ""
            prereqs = f" (requires: {', '.join(obj.prerequisites)})" if obj.prerequisites else ""
            lines.append(f"  - [{obj.objective_type}] {obj.description}{optional}{prereqs}")

    if quest.enemies:
        lines.append(f"\nEnemies ({len(quest.enemies)}):")
        for enemy in quest.enemies:
            boss = " [BOSS]" if enemy.is_boss else ""
            lines.append(f"  - {enemy.display_name}{boss} (HP:{enemy.hp}, DMG:{enemy.damage}, "
                         f"Location:{enemy.location}, Role:{enemy.narrative_role})")

    if quest.sub_quests:
        lines.append(f"\nSub-quests ({len(quest.sub_quests)}):")
        for sq in quest.sub_quests:
            lines.append(f"  - {sq.title}: {sq.description}")
            if sq.trigger_condition:
                lines.append(f"    Trigger: {sq.trigger_condition}")

    if quest.npc_dialogs:
        lines.append(f"\nNPC Dialogs ({len(quest.npc_dialogs)}):")
        for npc in quest.npc_dialogs:
            lines.append(f"  - {npc.npc_name} at {npc.location} ({len(npc.dialog_tree)} nodes)")
            for node in npc.dialog_tree[:3]:
                lines.append(f"    {node.speaker}: \"{node.text[:80]}...\"" if len(node.text) > 80
                             else f"    {node.speaker}: \"{node.text}\"")
                if node.choices:
                    for ch in node.choices:
                        lines.append(f"      -> [{ch.text}]")
            if len(npc.dialog_tree) > 3:
                lines.append(f"    ... ({len(npc.dialog_tree) - 3} more nodes)")

    if quest.puzzles:
        lines.append(f"\nPuzzles ({len(quest.puzzles)}):")
        for puzzle in quest.puzzles:
            lines.append(f"  - {puzzle.description} (Location: {puzzle.location})")

    if quest.lore_items:
        lines.append(f"\nLore Items ({len(quest.lore_items)}):")
        for lore in quest.lore_items:
            lines.append(f"  - {lore.title}: {lore.content[:100]}...")

    if quest.dynamic_events:
        lines.append(f"\nDynamic Events ({len(quest.dynamic_events)}):")
        for event in quest.dynamic_events:
            lines.append(f"  - {event.description} (Trigger: {event.trigger})")

    if quest.branching_consequences:
        lines.append(f"\nBranching Consequences ({len(quest.branching_consequences)}):")
        for bc in quest.branching_consequences:
            lines.append(f"  - {bc.description} (Trigger: {bc.trigger_choice})")

    if quest.rewards:
        lines.append(f"\nRewards ({len(quest.rewards)}):")
        for r in quest.rewards:
            lines.append(f"  - {r.item_name} ({r.item_type}) x{r.quantity}")

    return "\n".join(lines)


_METRIC_PROMPTS = {
    "narrative_coherence": (
        "Evaluate the NARRATIVE COHERENCE of this quest.\n"
        "Does the story make logical sense? Are plot points connected?\n"
        "Do character motivations make sense? Is there a clear beginning, middle, and end?\n"
        "Are there plot holes or contradictions?\n\n"
        "Score 1-5:\n"
        "  1 = Incoherent, random elements with no story logic\n"
        "  2 = Weak connections, major plot holes\n"
        "  3 = Acceptable story, some gaps but generally follows\n"
        "  4 = Good narrative flow, minor issues only\n"
        "  5 = Excellent, tight narrative with everything connected\n\n"
        "Respond with ONLY this JSON: {\"score\": <1-5>, \"reasoning\": \"<your reasoning>\"}"
    ),
    "dialog_quality": (
        "Evaluate the DIALOG QUALITY of this quest.\n"
        "Are NPC conversations natural and engaging? Do different NPCs have distinct voices?\n"
        "Are player choices meaningful? Does dialog reveal character and advance the story?\n\n"
        "Score 1-5:\n"
        "  1 = No dialog or completely generic/robotic\n"
        "  2 = Basic functional dialog, no personality\n"
        "  3 = Decent dialog, some character comes through\n"
        "  4 = Good dialog with distinct voices and meaningful choices\n"
        "  5 = Excellent, memorable dialog that deepens the world\n\n"
        "Respond with ONLY this JSON: {\"score\": <1-5>, \"reasoning\": \"<your reasoning>\"}"
    ),
    "thematic_consistency": (
        "Evaluate the THEMATIC CONSISTENCY of this quest.\n"
        "Do all components fit the stated theme? Are enemies, locations, items, and dialog\n"
        "all appropriate for the setting? Does the tone stay consistent?\n\n"
        "Score 1-5:\n"
        "  1 = Theme is ignored, elements feel randomly assembled\n"
        "  2 = Some elements fit but many feel out of place\n"
        "  3 = Generally on-theme with a few mismatches\n"
        "  4 = Strong thematic coherence, minor deviations\n"
        "  5 = Perfect thematic unity, every element reinforces the setting\n\n"
        "Respond with ONLY this JSON: {\"score\": <1-5>, \"reasoning\": \"<your reasoning>\"}"
    ),
    "player_engagement": (
        "Evaluate the PLAYER ENGAGEMENT potential of this quest.\n"
        "Would this be fun to play? Is there variety in activities? Are there stakes?\n"
        "Do player choices feel impactful? Is the pacing good?\n\n"
        "Score 1-5:\n"
        "  1 = Boring, no reason to continue playing\n"
        "  2 = Mildly interesting but repetitive or lacking stakes\n"
        "  3 = Solid quest that most players would enjoy\n"
        "  4 = Engaging with good variety and meaningful decisions\n"
        "  5 = Exceptional, would be a highlight of any RPG\n\n"
        "Respond with ONLY this JSON: {\"score\": <1-5>, \"reasoning\": \"<your reasoning>\"}"
    ),
    "originality": (
        "Evaluate the ORIGINALITY of this quest.\n"
        "How creative is it compared to standard RPG quest tropes?\n"
        "Are there any surprising twists, unique mechanics, or fresh takes?\n"
        "Or is it a standard fetch/kill quest with generic fantasy elements?\n\n"
        "Score 1-5:\n"
        "  1 = Completely generic, every element is a tired trope\n"
        "  2 = Mostly derivative with minor variations\n"
        "  3 = Some creative elements mixed with standard fare\n"
        "  4 = Notably creative, fresh takes on familiar concepts\n"
        "  5 = Highly original, innovative quest design\n\n"
        "Respond with ONLY this JSON: {\"score\": <1-5>, \"reasoning\": \"<your reasoning>\"}"
    ),
}


def _evaluate_single_metric(
    quest_summary: str,
    metric_name: str,
    prompt: str,
    llm_client: OllamaClient,
) -> dict:
    """Evaluate a single metric using the LLM judge.

    Returns {"score": float, "reasoning": str}.
    Falls back to score=0 with error reasoning on failure.
    """
    full_prompt = f"Quest to evaluate:\n\n{quest_summary}\n\n{prompt}"

    response = llm_client.generate(
        prompt=full_prompt,
        system=JUDGE_SYSTEM_PROMPT,
    )

    if not response.success:
        return {
            "score": 0.0,
            "reasoning": f"LLM call failed: {response.error}",
        }

    parsed = extract_json(response.text)
    if parsed and isinstance(parsed, dict) and "score" in parsed:
        score = parsed["score"]
        # Clamp to valid range
        if isinstance(score, (int, float)):
            score = max(1.0, min(5.0, float(score)))
        else:
            score = 0.0
        reasoning = parsed.get("reasoning", "No reasoning provided")
        return {"score": score, "reasoning": str(reasoning)}

    # If JSON parsing failed, try to extract a number from the response
    return {
        "score": 0.0,
        "reasoning": f"Could not parse judge response: {response.text[:200]}",
    }


def evaluate_with_llm_judge(quest: QuestData, llm_client: OllamaClient) -> dict:
    """Evaluate quest quality using an LLM judge.

    Sends the quest summary to the LLM with evaluation prompts for each
    metric. The judge evaluates as a "veteran game designer" and does NOT
    know which pattern generated the quest (blind evaluation).

    Args:
        quest: The QuestData instance to evaluate.
        llm_client: OllamaClient for making LLM calls.

    Returns:
        Dict mapping metric name -> {"score": float (1-5), "reasoning": str}
        Metrics: narrative_coherence, dialog_quality, thematic_consistency,
                 player_engagement, originality
    """
    quest_summary = _build_quest_summary(quest)
    results = {}

    for metric_name, prompt in _METRIC_PROMPTS.items():
        results[metric_name] = _evaluate_single_metric(
            quest_summary, metric_name, prompt, llm_client,
        )

    return results
