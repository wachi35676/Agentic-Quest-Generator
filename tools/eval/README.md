# Evaluation harness

Computes the five paper metrics over batches of fully-automated game sessions.

## Quick start

```bash
# Smoke test — 8 total sessions (~5-15 min depending on Groq latency)
N=2 bash tools/eval/run_all.sh

# Full run — 60 total sessions (4 profiles × 15)
bash tools/eval/run_all.sh
```

PowerShell equivalent: `.\tools\eval\run_all.ps1`.

Outputs land in `tools/eval/results/`:

- `results.json` — per-session metrics (one record per session)
- `results.csv` — same data, flat columns, for spreadsheet/paper plots
- `summary.json` — flat means across all sessions
- `summary_per_profile.json` — same statistics broken down by profile (aggressive / cautious / explorer / completionist)
- `headline.json` — paper-grade headline numbers for each metric: mean, stdev, median, and 95% bootstrap CI ($B = 1000$, seed 42)

Raw event streams are kept in `tools/eval/sessions/*.jsonl` for re-aggregation later.

## Per-session timing caps

`scripts/eval/scripted_player.gd` constants:

| Constant | Default | Effect |
|---|---|---|
| `TICK_INTERVAL` | 0.4 s | How often the profile state machine runs `_choose_action()`. |
| `MAX_WALL_CLOCK_MS` | 90 000 ms | Hard wall-clock cap per session. Tuned for batch throughput; relax to `300 000` for human play. |
| `STUCK_TIMEOUT_MS` | 20 000 ms | If no progress (move / interact / kill) in this window, end the session. |
| `MAX_CHAPTERS` | 4 | Stop after this many orchestrator chapters spawned. |

## How it works

```
[run_all.sh]
   │
   │ for profile in {aggressive, cautious, explorer, completionist}:
   │   for i in 1..N:
   │     AGQ_EVAL=1 AGQ_PROFILE=$profile \
   │     godot --headless res://scenes/EvalSession.tscn
   │
   ▼
[scenes/EvalSession.tscn]   ──loads──>   [scenes/Main.tscn]
   │                                       │
   │ waits for world_ready signal          │ Main spawns hand-placed NPCs
   │                                       │ EvaluationLogger writes events
   │ instantiates a ScriptedPlayer         │
   ▼                                       ▼
[scripts/eval/profile_*.gd]              user://eval/<id>.jsonl
   - drives Player.scripted_set_velocity
   - clicks dialog buttons via signals
   - reports back to Wanderer
   - ends session on chapter cap or stuck
   │
   │ session_end → get_tree().quit(0)
   ▼
[run_all.sh] copies *.jsonl into tools/eval/sessions/
   │
   ▼
[tools/eval/runner.py]
   │ loads every .jsonl
   │ calls metrics.all_metrics(events, entities)
   ▼
results.json / results.csv / summary.json
```

The Godot side captures structured events whenever `AGQ_EVAL` is set. The Python side reads `.jsonl` and computes the metrics offline. No keyboard, mouse, or human input is involved at any stage.

## The five metrics

1. **Structural Adherence** — fraction of `quest_generated` events whose JSON parsed *and* passed schema validation. Surfaces avg sanitizer-fix count + avg attempts.
2. **Accuracy of Given Strings** — fraction of bundles whose entity references (NPCs / items / sheets / position hints) resolved against the authoritative catalog. Per-category error breakdown.
3. **Adaptation Rate** — `quest_revised` events per hour of session time. Measures how often the orchestrator chooses to continue vs close.
4. **Memory Consistency** — fraction of orchestration `memory_claims` whose `kind`+`params` match a real ledger entry. (Option A: structured claims emitted by the LLM, verified deterministically.)
5. **Replanning Latency** — wall-clock ms from `replan_triggered` to `replan_completed`, paired by `prev_quest_id`. Reports median, p95, max.

## Profiles

Each profile is a deterministic state machine that drives `Player` directly (no fake input events).

| Profile | Behaviour |
|---|---|
| `aggressive` | Walks to the nearest LLM-spawned NPC, attacks until kill. Reports back. Repeats. |
| `cautious` | Talks to each LLM NPC once (first non-end choice). Never attacks. Reports when done. |
| `explorer` | Cycles talk → give → kill across distinct NPCs. Reports between cycles. |
| `completionist` | Talks to each NPC twice, gives one item, kills the villain-role NPC. Reports. |

A session ends when:

- A scripted profile reaches its goal and emits `session_end` (most common)
- `MAX_CHAPTERS = 4` orchestrations have completed
- `STUCK_TIMEOUT_MS = 20s` of no progress (stuck detector)
- Hard `MAX_WALL_CLOCK_MS = 90s` wall-clock cap inside `ScriptedPlayer` (batch-tuned; relax for human play)
- Hard outer cap inside `EvalSession` (defensive)

## Adding a new profile

1. Subclass `ScriptedPlayer` in `scripts/eval/profile_<name>.gd`. Override `_choose_action()` and (if needed) `_drive_npc_dialog()`.
2. Add the case to `eval_session._attach_scripted_player()`'s `match` block.
3. Add the profile name to `PROFILES` in `run_all.sh` / `run_all.ps1`.

## Adjusting the schema

Event types live in `scripts/evaluation_logger.gd` (just a method, no schema enforcement) and the metrics that consume them live in `tools/eval/metrics.py`. Add new payload fields without breaking older sessions — the metric functions all use `.get(key, default)`.

## Re-running the aggregator without re-playing

```bash
python tools/eval/runner.py \
    --in tools/eval/sessions \
    --out tools/eval/results \
    --entities tools/eval/entities.json
```

Useful when you tweak metrics.py and want to re-aggregate over the same captured sessions.

## Troubleshooting

- **"GROQ_API_KEY not set"** — check `.env` in the project root.
- **All sessions return 429** — the LLM provider is rate-limited. Wait or rotate keys.
- **`session_end` reason `stuck`** — the scripted player got stuck (often: NPC spawned in a wall). Less common after the spawner's player-relative position fix, but it can still happen. The session is still useful — its `quest_generated` event was logged.
- **Zero `memory_claim` events** — the model isn't emitting claims. Check `prompts.gd::build_orchestration_system_prompt` includes the `memory_claims` instructions.
