"""Agentic Quest Generator — CLI entry point.

Usage:
    python main.py generate --pattern react --task dark_forest_medium
    python main.py generate --pattern react --task dark_forest_medium --output quest.json
    python main.py play --quest path/to/quest.json
    python main.py evaluate --tasks all --patterns all
    python main.py evaluate --tasks dark_forest_medium --patterns react,reflection
    python main.py list-tasks
    python main.py check-ollama
"""

import argparse
import json
import os
import sys
import time

from config import CONFIG
from llm.client import OllamaClient
from agents.react import ReActPattern
from agents.reflection import ReflectionPattern
from agents.tree_of_thought import TreeOfThoughtPattern
from agents.critic import CriticPattern
from agents.plan_execute import PlanExecutePattern
from agents.base import GenerationTask, WorldState
from tasks.task_bank import get_task, get_all_tasks, TASKS
from quests.validator import validate_quest


PATTERNS = {
    "react": ReActPattern,
    "reflection": ReflectionPattern,
    "tot": TreeOfThoughtPattern,
    "critic": CriticPattern,
    "plan_execute": PlanExecutePattern,
}


def cmd_generate(args):
    """Generate a quest using a specified pattern."""
    # Get the task
    task = get_task(args.task)
    print(f"Task: {task.task_id} | Theme: {task.theme} | Difficulty: {task.difficulty}")
    print(f"Pattern: {args.pattern}")
    print("-" * 60)

    # Create LLM client and check connection
    client = OllamaClient()
    if not client.check_connection():
        print("ERROR: Cannot connect to Ollama or model not available.")
        print(f"  URL: {CONFIG.ollama_base_url}")
        print(f"  Model: {CONFIG.model_name}")
        print("  Make sure Ollama is running: ollama serve")
        sys.exit(1)

    print(f"Connected to Ollama ({CONFIG.model_name})")

    # Create the pattern
    if args.pattern not in PATTERNS:
        print(f"ERROR: Unknown pattern '{args.pattern}'. Available: {', '.join(PATTERNS.keys())}")
        sys.exit(1)

    pattern = PATTERNS[args.pattern](llm_client=client)

    # Generate
    print(f"\nGenerating quest... (this may take a few minutes with {CONFIG.model_name})")
    world_state = WorldState(available_zones=list(CONFIG.world_zones))
    quest = pattern.generate(task, world_state)

    # Validate
    validation = validate_quest(quest)
    print(f"\nValidation: {'PASSED' if validation.is_valid else 'FAILED'} (score: {validation.score:.2f})")
    if validation.errors:
        for err in validation.errors:
            print(f"  ERROR: {err}")
    if validation.warnings:
        for warn in validation.warnings:
            print(f"  WARN: {warn}")

    # Save
    if args.output:
        output_path = args.output
    else:
        output_dir = os.path.join(CONFIG.generated_quests_dir, args.pattern)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{quest.id}.json")

    quest.save(output_path)
    print(f"\nQuest saved to: {output_path}")
    print(f"Trace saved to: {CONFIG.traces_dir}/")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Quest: {quest.title}")
    print(f"Description: {quest.description}")
    print(f"Storyline beats: {len(quest.storyline)}")
    print(f"Objectives: {len(quest.objectives)}")
    print(f"Enemies: {len(quest.enemies)}")
    print(f"Sub-quests: {len(quest.sub_quests)}")
    print(f"NPC Dialogs: {len(quest.npc_dialogs)}")
    print(f"Rewards: {len(quest.rewards)}")
    print(f"Puzzles: {len(quest.puzzles)}")
    print(f"Lore Items: {len(quest.lore_items)}")
    print(f"Dynamic Events: {len(quest.dynamic_events)}")
    print(f"Branching Consequences: {len(quest.branching_consequences)}")
    print(f"Generation time: {quest.generation_duration_seconds:.1f}s")
    print(f"LLM calls: {quest.llm_calls_count}")


def cmd_evaluate(args):
    """Run evaluation comparing patterns on tasks."""
    from evaluation.comparator import Comparator
    from evaluation.reporter import generate_report

    # Parse tasks
    if args.tasks == "all":
        tasks = get_all_tasks()
    else:
        task_ids = [t.strip() for t in args.tasks.split(",")]
        tasks = []
        for tid in task_ids:
            try:
                tasks.append(get_task(tid))
            except ValueError as e:
                print(f"ERROR: {e}")
                sys.exit(1)

    # Parse patterns
    if args.patterns == "all":
        selected_patterns = dict(PATTERNS)
    else:
        pattern_names = [p.strip() for p in args.patterns.split(",")]
        selected_patterns = {}
        for pname in pattern_names:
            if pname not in PATTERNS:
                print(f"ERROR: Unknown pattern '{pname}'. Available: {', '.join(PATTERNS.keys())}")
                sys.exit(1)
            selected_patterns[pname] = PATTERNS[pname]

    print(f"Evaluation Configuration:")
    print(f"  Tasks: {len(tasks)} ({', '.join(t.task_id for t in tasks)})")
    print(f"  Patterns: {len(selected_patterns)} ({', '.join(selected_patterns.keys())})")
    print(f"  Total runs: {len(tasks) * len(selected_patterns)}")
    print("=" * 60)

    # Create LLM client and check connection
    client = OllamaClient()
    if not client.check_connection():
        print("ERROR: Cannot connect to Ollama or model not available.")
        print(f"  URL: {CONFIG.ollama_base_url}")
        print(f"  Model: {CONFIG.model_name}")
        print("  Make sure Ollama is running: ollama serve")
        sys.exit(1)

    print(f"Connected to Ollama ({CONFIG.model_name})")

    # Set up output directory
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(CONFIG.eval_results_dir, f"run_{timestamp}")

    # Run comparison
    comparator = Comparator(
        llm_client=client,
        patterns=selected_patterns,
        tasks=tasks,
    )
    result = comparator.run_comparison(output_dir=output_dir)

    # Generate report with charts
    print("\nGenerating report...")
    generate_report(result, output_dir=output_dir)

    # Print aggregate summary
    print(f"\n{'=' * 60}")
    print("AGGREGATE RESULTS")
    print(f"{'=' * 60}")
    for pattern, metrics in result.aggregate.items():
        print(f"\n  {pattern}:")
        for metric, stats in sorted(metrics.items()):
            print(f"    {metric}: mean={stats['mean']:.3f} std={stats['std']:.3f} "
                  f"[{stats['min']:.3f}, {stats['max']:.3f}]")

    print(f"\nFull results saved to: {output_dir}")


def cmd_list_tasks(args):
    """List all available generation tasks."""
    print("Available generation tasks:\n")
    for task_id, task in TASKS.items():
        print(f"  {task_id}")
        print(f"    Theme: {task.theme} | Difficulty: {task.difficulty}")
        print(f"    {task.description[:80]}...")
        print()


def cmd_play(args):
    """Launch the Pygame game with a quest JSON file."""
    quest_path = args.quest
    if not os.path.exists(quest_path):
        print(f"ERROR: Quest file not found: {quest_path}")
        sys.exit(1)
    print(f"Loading quest: {quest_path}")
    from game.engine import run_game
    run_game(quest_path)


def cmd_check_ollama(args):
    """Check Ollama connection and available models."""
    import subprocess

    client = OllamaClient()
    print(f"Ollama command: {client.ollama_cmd}")
    print(f"Target model: {CONFIG.model_name}")

    try:
        p = subprocess.run(
            [client.ollama_cmd, "list"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        out = p.stdout.decode("utf-8", errors="ignore").strip()
        print(f"\nAvailable models:")
        for line in out.split("\n"):
            marker = " <-- target" if CONFIG.model_name in line else ""
            print(f"  {line}{marker}")

        if client.check_connection():
            print(f"\nStatus: READY")
        else:
            print(f"\nStatus: Model '{CONFIG.model_name}' not found. Pull it with: ollama pull {CONFIG.model_name}")
    except FileNotFoundError:
        print(f"\nStatus: '{client.ollama_cmd}' not found. Is Ollama installed?")
    except Exception as e:
        print(f"\nStatus: CANNOT CONNECT ({e})")


def main():
    parser = argparse.ArgumentParser(description="Agentic Quest Generator")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate a quest")
    gen_parser.add_argument("--pattern", required=True, choices=list(PATTERNS.keys()),
                           help="Agentic pattern to use")
    gen_parser.add_argument("--task", required=True, help="Task ID from task bank")
    gen_parser.add_argument("--output", help="Output file path (optional)")

    # evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate and compare patterns")
    eval_parser.add_argument("--tasks", default="all",
                             help="Comma-separated task IDs or 'all' (default: all)")
    eval_parser.add_argument("--patterns", default="all",
                             help="Comma-separated pattern names or 'all' (default: all)")

    # play command
    play_parser = subparsers.add_parser("play", help="Play a generated quest in Pygame")
    play_parser.add_argument("--quest", required=True, help="Path to quest JSON file")

    # list-tasks command
    subparsers.add_parser("list-tasks", help="List available tasks")

    # check-ollama command
    subparsers.add_parser("check-ollama", help="Check Ollama connection")

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "play":
        cmd_play(args)
    elif args.command == "list-tasks":
        cmd_list_tasks(args)
    elif args.command == "check-ollama":
        cmd_check_ollama(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
