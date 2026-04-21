# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Academic research project comparing five agentic LLM patterns — **ReAct, Reflection, Tree-of-Thought, Critic, and Plan & Execute** — on the task of generating structured game quests for a Pygame RPG. Each pattern produces the same `QuestData` contract so they can be scored on identical tasks. The Pygame client plays generated quests and emits runtime events back into the patterns' `adapt()` method for live quest modification.

The LLM backend is **Ollama running locally** (default model `llama3.1`, see `config.py`). The client in `llm/client.py` shells out via `subprocess` to `ollama run <model>` (auto-detects `ollama.exe` on WSL) — it does not use the HTTP API despite `ollama_base_url` appearing in config.

## Commands

All commands run through `main.py`. Ollama must be running (`ollama serve`) with the target model pulled.

```bash
# Sanity-check Ollama connection + model availability
python main.py check-ollama

# List tasks defined in tasks/task_bank.py
python main.py list-tasks

# Generate one quest with one pattern
python main.py generate --pattern react --task dark_forest_medium
python main.py generate --pattern reflection --task undead_crypt_hard --output out.json

# Full evaluation sweep (all patterns × all tasks) — writes to evaluation/results/run_<timestamp>/
python main.py evaluate --tasks all --patterns all
python main.py evaluate --tasks dark_forest_medium --patterns react,reflection

# Play a generated quest in Pygame (enables runtime adaptation loop)
python main.py play --quest quests/generated/react/<id>.json
```

Valid `--pattern` values: `react`, `reflection`, `tot`, `critic`, `plan_execute` (see `PATTERNS` dict in `main.py`).

Dependencies: `pip install -r requirements.txt` (pygame, requests, matplotlib, scipy). There is no test runner, linter, or build system configured — `tests/` contains only an empty `__init__.py`.

## Architecture

### Central data contract: `quests/schema.py`

Every pattern produces a `QuestData` dataclass; the game consumes it; the evaluator scores it. Do not introduce parallel quest representations — extend `QuestData` and its nested dataclasses (`QuestObjective`, `EnemyEncounter`, `SubQuest`, `NPCDialog`/`DialogLine`/`DialogChoice`, `EnvironmentalPuzzle`, `LoreItem`, `DynamicEvent`, `BranchingConsequence`). Each has `to_dict` / `from_dict` for JSON round-trip; `QuestData.save()` / `load()` persist to disk.

`quests/validator.py` enforces structural constraints (ID references, objective prerequisites, dialog node links, etc.) and returns a score used both for generation feedback and evaluation metrics.

### Pattern interface: `agents/base.py`

`AgenticPattern` is the ABC that all five patterns implement. Two methods matter:

- `generate(task: GenerationTask, world_state: WorldState) -> QuestData` — the offline pre-generation phase; the pattern runs its full reasoning loop.
- `adapt(adaptation_task: AdaptationTask) -> QuestModification` — the online phase; invoked from the running game to produce a diff against the active quest.

Each pattern lives in its own file (`react.py`, `reflection.py`, `tree_of_thought.py`, `critic.py`, `plan_execute.py`) and shares prompts under `agents/prompts/`. Per-pattern budgets (max steps, rounds, branching, tokens, retries) are centralised in `config.py` — tune there, not in the pattern files.

### LLM layer: `llm/`

- `client.py` — `OllamaClient` subprocess wrapper producing `LLMResponse`. Two temperatures in `CONFIG`: `default_temperature` (creative) and `structured_temperature` (scoring/planning/JSON).
- `parser.py` — JSON repair / extraction from LLM output (budget `json_repair_max_attempts`).
- `prompts.py` — shared prompt fragments.

### Evaluation: `evaluation/`

`comparator.py` runs (pattern × task) matrix; `metrics.py` computes LLM-free structural metrics (completeness, validity via `validate_quest`, complexity, branching, consistency); `llm_judge.py` adds LLM-as-judge scoring; `statistics.py` aggregates across runs (means, std, min/max); `reporter.py` renders matplotlib charts. Results land in `evaluation/results/run_<timestamp>/`.

### Game + runtime adaptation: `game/` and `runtime/`

`game/engine.py` is the Pygame main loop with a state machine (`exploration`, `combat`, `dialog`, `quest_log`, `inventory`, …). As the player acts, the engine emits typed events from `runtime/events.py` (`EVENT_BOSS_DEFEATED`, `EVENT_NPC_KILLED`, `EVENT_BRANCHING_CHOICE`, …) to `runtime/adapter.py`.

`RuntimeAdapter` decides which events warrant adaptation, packages a `GameStateSnapshot` + current `QuestData` into an `AdaptationTask`, and calls the selected pattern's `adapt()` **on a background thread** (`runtime/threading_utils.py`) so the game loop does not block on LLM latency. There is a 30-second cooldown (`ADAPTATION_COOLDOWN`) and only one pending adaptation at a time. Returned `QuestModification` is then merged into the live quest.

When modifying game code, keep the rule: **the Pygame thread must never call the LLM synchronously.** All LLM work goes through `BackgroundTask`.

### Tracing: `tracing/logger.py`

Every `generate()` / `adapt()` call instantiates a `TraceLogger` (via `AgenticPattern._create_tracer`) that records every step, prompt, and LLM response to `tracing/traces/`. These traces are the primary research artifact — do not silently drop logging when refactoring patterns.

### World vocabulary

`CONFIG.world_zones` is a **fixed tuple** constraining LLM output. Quests reference zones by these exact strings; `game/world.py` and the validator rely on the vocabulary staying closed. Add new zones in `config.py` and ensure `game/assets/` has matching content before using them in prompts or tasks.

## Conventions worth preserving

- Dataclasses everywhere for quest data; all serializable via explicit `to_dict` / `from_dict` (no `dataclasses.asdict` — nested types need custom handling).
- Pattern output paths: `quests/generated/<pattern>/<quest_id>.json`.
- `GenerationTask.required_elements` and `constraints` are free-form strings/dicts that prompts translate into natural-language requirements — the validator does *not* enforce them; scoring does.
- `config.py` holds a frozen dataclass exported as `CONFIG`; import `CONFIG`, don't instantiate `Config()`.
