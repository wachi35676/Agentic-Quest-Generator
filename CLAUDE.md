# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Godot 4.6.2 (GDScript) top-down adventure where an LLM generates the quests in real time. Story is driven by a single hand-placed NPC ("the Wanderer") who acts as the *orchestrator*: he hands out the first chapter, then on each subsequent talk reads a ledger of what the player did and either issues a continuation chapter or closes the arc.

There is no README. The plan-of-record for the orchestrator design lives at `~/.claude/plans/hello-so-we-are-velvety-cookie.md`.

## Common commands

The Godot binary lives at `/c/Users/wasif/Downloads/Godot_v4.6.2-stable_win64.exe/Godot_v4.6.2-stable_win64.exe` (visible) and `..._console.exe` (headless). All commands run from the project root.

```bash
# Parse-check (fast, no run)
.../Godot_v4.6.2-stable_win64_console.exe --headless --path . --quit-after 2

# Re-import after adding new .gd files / .tscn / textures (registers class_name)
.../Godot_v4.6.2-stable_win64_console.exe --headless --path . --import

# Launch the game (player-visible)
.../Godot_v4.6.2-stable_win64.exe --path .

# Run the test scenes (headless)
.../Godot_v4.6.2-stable_win64_console.exe --headless --path . res://scenes/Test.tscn         # unit tests
.../Godot_v4.6.2-stable_win64_console.exe --headless --path . res://scenes/TestPlay.tscn     # playthrough DSL
.../Godot_v4.6.2-stable_win64_console.exe --headless --path . res://scenes/TestLLM.tscn      # validator + spawner against fixture; AGQ_OLLAMA_LIVE=1 also calls the LLM
.../Godot_v4.6.2-stable_win64_console.exe --headless --path . res://scenes/TestSanitizer.tscn  # offline sanitizer iteration against user://llm_debug/<tag>.txt dumps
```

When you add a new file with `class_name X`, run `--import` once before parse-checks; otherwise other scripts that reference `X` fail with "nonexistent function 'new'". Test scenes set `get_tree().set_meta("skip_autogen", true)` to suppress auto-kickoff (`main._maybe_kickoff` checks this) — preserve that contract when editing the kickoff path.

## Architecture

### LLM stack (`scripts/llm/`)

Provider clients all expose the same `generate(model, system, user, options, format) -> {ok, text, error}`:

- `groq_client.gd` — primary. Reads `GROQ_API_KEY*` (multiple) from `.env`, rotates on 429. Uses OpenAI-compatible chat completions. `format="json"` → `response_format: {type: "json_object"}`.
- `gemini_client.gd` — fallback. Reads `GEMINI_API_KEY*`. Uses `:generateContent`. `format="json"` → `responseMimeType`. Gates `thinkingConfig` to gemini-3+ models only.
- `ollama_client.gd` — legacy local provider, unused but kept.
- `composite_client.gd` — wraps Groq + Gemini. Tries Groq; on 429 / "rate limit" / "tokens per day", marks Groq blocked for 5 minutes and falls through to Gemini. **All higher-level code uses CompositeClient via `QuestGenAgent`, not the individual clients.**
- `env_loader.gd` — reads `.env` once. `EnvLoader.get_keys_with_prefix("GROQ_API_KEY")` returns all matching keys for rotation.

`quest_gen_agent.gd` is the only entry point most callers need. Models are `@export`'d: `model = "llama-3.3-70b-versatile"` for big-bundle paths, `expand_model = "llama-3.1-8b-instant"` for small/fast paths. Methods:

- `generate(premise)` — legacy single-call branching bundle (auto-kickoff path).
- `generate_branching(quest_giver, role)` — Wanderer's first chapter. Full bundle with sanitize + validate + repair loop.
- `generate_orchestration(prev_summary, ledger, current_npcs, giver, max_remaining)` — the **Wanderer-orchestrator** call. Reads the action ledger and returns either `{decision: "continue", new_quest, wanderer_dialog}` or `{decision: "complete", rewards, wanderer_dialog}`.
- `generate_simple(npc, role, kind)` — fetch / kill quests for the simple-quest NPCs (Farmer, Hunter, Old Sage).
- `generate_stage1` / `generate_stage2` — Mystic two-stage quest.
- `expand_node(ctx)` — single-node lazy dialog expansion when a choice's `next == "__expand__"`.

Every LLM response goes through **sanitize → validate** before reaching the engine:

- `quest_sanitizer.gd` — deterministic cleanup of common LLM quirks. ASCII-only ids, snap unknown character_sheet to nearest of the 6 sheets via Levenshtein + role keywords, strip whitespace from action verbs, drop unknown items from `initial_items`, drop objectives referencing unknown NPCs, case-fix `wanderer → Wanderer`, auto-inject "report back" objective if a branch has only one, strip `die` actions from NPCs that are required for objectives, etc. The sanitizer is the *only* reason raw LLM output is usable; treat it as load-bearing.
- `quest_validator.gd` — pure validation. `validate(bundle, extra_known_npcs)` returns `Array[String]` of human-readable errors. `extra_known_npcs` lets objectives reference world NPCs that aren't in `bundle.npcs[]` (the hand-placed Wanderer).

Prompts live in `prompts.gd` as static functions. `build_branching_system_prompt` puts the world-constraints (no locations / time-of-day / follow-me) at BOTH the top and bottom of the prompt — LLMs over-weight first/last instructions. The branching path skips the heirloom-quest fixture (`build_system_prompt(false)`) because it's ~3K tokens and pushes Groq's per-minute TPM cap.

### Quest data + flow (`scripts/quest*.gd`)

- `quest.gd` — `Quest` + nested `Branch` + `Objective` (in `objective.gd`). `Quest.from_dict(d)` is the canonical ingest. `Quest.meta` is a free-form dict; `meta.orchestrator_managed = true` makes `evaluate()` short-circuit to `"active"` so the Wanderer is the only thing that can close the quest.
- `quest_manager.gd` — autoload. Owns `active_quests` + `completed_quests`, listens to `Game` signals, dispatches events to objectives. **`action_ledger: Array`** accumulates story-significant player actions (`kill_npc`, `npc_give`, `npc_take`, `dialog_choice`) capped at 20 entries. `record_action` is called from the existing `_on_npc_killed` / `_on_npc_interacted` paths. `clear_ledger()` is called when the orchestrator closes a quest.
- `quest_spawner.gd` — takes a bundle dict, wipes existing LLM-spawned NPCs/Items/Labels (`_wipe`), spawns the new ones with positions resolved via compass-hint offsets around the player, registers the quest in `QuestManager`. Sets `quest.meta.orchestrator_managed = true` if the bundle's quest dict has the same flag set. Pass `keep_array` (an Array of Nodes) to preserve the hand-placed quest-givers across the wipe.
- `quest_log.gd` — Tab UI. Lists `active_quests` + `completed_quests`. Branch entries dim grey when locked.

### Wanderer orchestrator (the central new flow)

`main.gd::_handle_branching` is a four-state machine on `npc.memory`:

| State | Trigger | Effect |
|---|---|---|
| `idle` | first talk | `[Yes]` → `_kickoff_first_chapter` (calls `generate_branching`) |
| `active` empty ledger | re-talk before doing anything | `[Bye]` only — no LLM cost |
| `active` ledger ≥ 1 | re-talk after acting | `[Report]` → `_orchestrate_next_chapter` |
| `closing` | LLM call in flight | dialog locked while awaiting |

Constants: `MAX_ORCHESTRATIONS = 5` per quest. After 5 talks, the engine forces `decision = complete` regardless of LLM output. If the LLM picks `complete` with <2 ledger entries, override to `continue` (story can't end before player acts). If `decision == continue` but `new_quest.npcs[]` is empty, `generate_orchestration` rejects (forces a retry on next `[Report]`) — orphan chapters with nothing to interact with are the most common LLM failure mode.

The Wanderer is **invulnerable** (`npc.gd::_on_hurt` early-returns when `has_meta("quest_giver_kind")`) so an errant attack can't softlock the quest.

### Hand-placed NPCs (in `main._spawn_quest_givers`)

| Name | Kind | Position | Flow |
|---|---|---|---|
| Wanderer | `branching` | (-288, -120) | orchestrator (above) |
| Farmer | `fetch` | (0, 0) | simple `give:item` quest |
| Hunter | `kill` | (-80, -128) | simple `kill_enemy` quest |
| Old Sage | `fetch` | (128, 32) | simple `give:item` quest |
| Mystic | `two_stage` | (-32, 96) | `generate_stage1` → moral choice → `generate_stage2` |

`_handle_quest_giver` dispatches on `quest_giver_kind` meta. Each kind has its own state machine on `npc.memory`. Floating name labels are children of the NPC node (so `queue_free` on the NPC also frees the label) — adding labels as siblings to `level_root` was the classic "stale name tag" bug.

### World

The map is the imported NinjaAdventure CC0 village (`content/map/map_village.tscn` + `tileset.tres` + 5 atlas PNGs). `main.gd` instantiates the village scene as `level_root` instead of building a procedural floor. Tile bounds were extracted via Python: x ∈ [-432, 224], y ∈ [-240, 320] in world pixels. Camera limits + perimeter walls are derived from those bounds in `_setup_camera` / `_add_world_walls`.

Camera is a custom `CameraGrid` (`scripts/camera_grid.gd`), a port of NinjaAdventure's room-by-room camera: 320×176 px cells, sine-eased 0.8s tween between rooms, viewport 640×352 with zoom 2 so visible == cell.

### Autoloads (`project.godot`)

- `ItemDB` — `res://scripts/item_db.gd`. Closed-set item catalog. `ItemDB.has(id)`, `ItemDB.weapon_stats(id)`.
- `Game` — `res://scripts/game.gd`. Signal hub: `npc_killed`, `npc_interacted`, `item_picked_up`, etc. Plus `Game.log_event(tag, data)`.
- `QuestManager` — `res://scripts/quest_manager.gd`. Active/completed quest state, action ledger, signal-driven dispatch.

## Things to know when editing

- `.env` holds `GROQ_API_KEY`, `GROQ_API_KEY2`, `GROQ_API_KEY3`, `GEMINI_API_KEY`, `GEMINI_API_KEY2`, `GEMINI_API_KEY3`. `EnvLoader.get_keys_with_prefix` returns all matching. Don't hardcode keys; rotation is automatic.
- LLM raw responses are dumped to `user://llm_debug/<tag>.txt` (= `%APPDATA%/Godot/app_userdata/Agentic Quest Generator/llm_debug/`). `TestSanitizer.tscn --tag=initial` re-runs sanitize+validate against a dump for offline iteration.
- The orchestration prompt forbids: any specific location (mine/windmill/inn/cave/forest/...), time-of-day, "follow me / accompany / lead-me-to" mechanics, and unimplementable cryptic clues. The forbidden list lives at top + bottom of the prompt; if the LLM regresses on this, strengthen those blocks rather than adding code-side filters.
- `__expand__` lazy expansion is on-demand only; the prefetcher was disabled because the single shared `HTTPRequest` in each client can't run concurrent calls.
- `quest_spawner._wipe` sweeps `NPC`, `ItemPickup`, and `Label` direct-children of `level_root`. Don't add narrative labels as `level_root` siblings — make them children of an NPC.
- `Quest.evaluate()` short-circuits to `"active"` when `meta.orchestrator_managed`. Don't add new branch/fail-condition logic that bypasses this — closure must go through the Wanderer.
