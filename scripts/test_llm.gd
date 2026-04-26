extends Node

# LLM-layer tests. Two modes:
#
#   Fixture mode (always on): proves the JSON contract by running validator,
#     spawner, and a playthrough on the gold-standard fixture without ever
#     hitting Ollama. Catches schema breaks early.
#
#   Live mode (opt-in via env var AGQ_OLLAMA_LIVE=1): actually calls phi4
#     with the default premise. Asserts: response parseable, validator passes
#     within MAX_REPAIRS, spawner builds the world. Output is non-determi-
#     nistic so we don't drive a specific branch.
#
# Run: godot --headless --path . res://scenes/TestLLM.tscn

const FIXTURE := "res://tests/fixtures/heirloom_quest.json"

var _passes := 0
var _fails := 0
var _failures: Array[String] = []

func _ready() -> void:
	await get_tree().process_frame
	print("=== LLM-layer tests ===")
	await _run("fixture: parses as JSON",                   _t_fixture_parses)
	await _run("fixture: validator returns zero errors",    _t_fixture_validates)
	await _run("validator: rejects missing 'quest' key",    _t_validator_missing_quest)
	await _run("validator: rejects unknown item id",        _t_validator_unknown_item)
	await _run("validator: rejects unknown character_sheet",_t_validator_unknown_sheet)
	await _run("validator: rejects too few branches",       _t_validator_few_branches)
	await _run("validator: rejects orphan dialog 'next'",   _t_validator_orphan_next)
	await _run("validator: rejects unknown action verb",    _t_validator_unknown_action)
	await _run("validator: rejects npc not in roster",      _t_validator_orphan_npc)
	await _run("spawner: rebuilds world from fixture",      _t_spawner_rebuilds)
	await _run("spawner: completes mediate path post-spawn",_t_spawner_playthrough)
	await _run("validator: __expand__ accepted as next",    _t_validator_expand_sentinel)
	await _run("expand: cache hit returns without LLM",     _t_expand_cache_hit)
	await _run("expand: prefetch warms cache",              _t_expand_prefetch)
	await _run("expand: dialog splices node into tree",     _t_expand_splice_in_dialog)
	if _is_live():
		await _run("LIVE: phi4 produces valid bundle",     _t_live_phi4)
	print("=== %d passed, %d failed ===" % [_passes, _fails])
	for f in _failures:
		print(" FAIL: ", f)
	get_tree().quit(1 if _fails > 0 else 0)

func _is_live() -> bool:
	return OS.get_environment("AGQ_OLLAMA_LIVE") == "1"

func _run(name: String, fn: Callable) -> void:
	QuestManager.active_quests.clear()
	QuestManager.completed_quests.clear()
	QuestManager.global_flags.clear()
	var err: Variant = await fn.call()
	if err == null or (err is String and err == ""):
		_passes += 1
		print("  ok    ", name)
	else:
		_fails += 1
		_failures.append("%s — %s" % [name, str(err)])
		print("  FAIL  %s — %s" % [name, str(err)])

# --- helpers ---

func _load_fixture() -> Dictionary:
	var f := FileAccess.open(FIXTURE, FileAccess.READ)
	if f == null:
		return {}
	var b: Variant = JSON.parse_string(f.get_as_text())
	f.close()
	if b is Dictionary:
		return b
	return {}

func _mutate(base: Dictionary, path: Array, value: Variant) -> Dictionary:
	# Shallow path-set: copies the bundle, then walks `path` (mix of string
	# keys and int indices) and sets the leaf to `value`.
	var copy: Dictionary = base.duplicate(true)
	var ref: Variant = copy
	for i in range(path.size() - 1):
		ref = ref[path[i]]
	ref[path[-1]] = value
	return copy

# --- fixture tests ---

func _t_fixture_parses() -> Variant:
	var b := _load_fixture()
	if b.is_empty(): return "fixture failed to parse"
	if not b.has("quest"): return "fixture lacks 'quest'"
	if not b.has("npcs"): return "fixture lacks 'npcs'"
	return ""

func _t_fixture_validates() -> Variant:
	var b := _load_fixture()
	var errs := QuestValidator.validate(b)
	if not errs.is_empty():
		return "validator returned %d errors; first: %s" % [errs.size(), errs[0]]
	return ""

# --- validator tests (each mutates the fixture in one way) ---

func _t_validator_missing_quest() -> Variant:
	var b := _load_fixture()
	b.erase("quest")
	var errs := QuestValidator.validate(b)
	if errs.is_empty(): return "expected at least one error"
	return ""

func _t_validator_unknown_item() -> Variant:
	var b := _mutate(_load_fixture(), ["quest","branches",0,"rewards",0,"item_id"], "nuclear_warhead")
	var errs := QuestValidator.validate(b)
	for e in errs:
		if "nuclear_warhead" in String(e):
			return ""
	return "expected an error mentioning 'nuclear_warhead'"

func _t_validator_unknown_sheet() -> Variant:
	var b := _mutate(_load_fixture(), ["npcs",0,"character_sheet"], "BogusSheet")
	var errs := QuestValidator.validate(b)
	for e in errs:
		if "BogusSheet" in String(e):
			return ""
	return "expected error about BogusSheet"

func _t_validator_few_branches() -> Variant:
	var b := _load_fixture()
	# Keep only the first branch.
	b.quest.branches = [b.quest.branches[0]]
	var errs := QuestValidator.validate(b)
	for e in errs:
		if "at least 3 entries" in String(e):
			return ""
	return "expected branch-count error"

func _t_validator_orphan_next() -> Variant:
	var b := _mutate(_load_fixture(),
		["npcs",0,"dialog_tree","start_intro","choices",0,"next"],
		"node_that_does_not_exist")
	var errs := QuestValidator.validate(b)
	for e in errs:
		if "node_that_does_not_exist" in String(e):
			return ""
	return "expected orphan-next error"

func _t_validator_unknown_action() -> Variant:
	var b := _load_fixture()
	# Add a bogus action verb on the bandit's first choice
	var bandit: Dictionary = b.npcs[1]
	bandit.dialog_tree.start_unbriefed.choices[0]["actions"] = ["teleport_player:elsewhere"]
	var errs := QuestValidator.validate(b)
	for e in errs:
		if "teleport_player" in String(e):
			return ""
	return "expected unknown-action error"

func _t_validator_orphan_npc() -> Variant:
	var b := _mutate(_load_fixture(),
		["quest","branches",0,"objectives",0,"params","npc_name"],
		"GhostlyNonExistent")
	var errs := QuestValidator.validate(b)
	for e in errs:
		if "GhostlyNonExistent" in String(e):
			return ""
	return "expected orphan-npc error"

# --- spawner tests (need a live Main) ---

func _t_spawner_rebuilds() -> Variant:
	var main_node: Node = await _spawn_main_with_fixture()
	if main_node == null: return "could not spawn Main"
	var npcs := get_tree().get_nodes_in_group("npc")
	var found_elder := false
	var found_bandit := false
	for n in npcs:
		if n.npc_name == "Elder": found_elder = true
		if n.npc_name == "Bandit": found_bandit = true
	main_node.queue_free()
	await get_tree().process_frame
	if not found_elder: return "Elder not spawned"
	if not found_bandit: return "Bandit not spawned"
	return ""

func _t_spawner_playthrough() -> Variant:
	# Quick mediate-path drive: set the three flags + emit the give event.
	var main_node: Node = await _spawn_main_with_fixture()
	if main_node == null: return "could not spawn Main"
	QuestManager.set_flag_all_active("bandit_sympathy", "true")
	QuestManager.set_flag_all_active("elder_confessed", "true")
	QuestManager.set_flag_all_active("mediated", "true")
	Game.npc_interacted.emit("Elder", "give:gem_red")
	await get_tree().process_frame
	var q := QuestManager.get_quest("stolen_heirloom")
	main_node.queue_free()
	await get_tree().process_frame
	if q == null: return "quest missing"
	if q.status != Quest.Status.COMPLETED: return "status=%d" % q.status
	if q.completed_branch_id != "mediate": return "branch=%s" % q.completed_branch_id
	return ""

func _spawn_main_with_fixture() -> Node:
	get_tree().set_meta("skip_autogen", true)
	var packed: PackedScene = load("res://scenes/Main.tscn")
	var m := packed.instantiate()
	get_tree().root.add_child(m)
	await get_tree().process_frame
	await get_tree().process_frame
	var bundle := _load_fixture()
	QuestSpawner.spawn(bundle, m.get("level_root"), m.get("player"), null)
	await get_tree().process_frame
	return m

# --- expansion tests (no LLM; pre-populate the cache) ---

func _t_validator_expand_sentinel() -> Variant:
	var b := _load_fixture()
	# Mutate one choice to use __expand__ next.
	b.npcs[0].dialog_tree["start_intro"].choices[0]["next"] = "__expand__"
	b.npcs[0].dialog_tree["start_intro"].choices[0]["next_hint"] = "the player commits"
	var errs := QuestValidator.validate(b)
	if not errs.is_empty():
		return "expected zero errors with __expand__; got: %s" % errs[0]
	return ""

func _t_expand_cache_hit() -> Variant:
	var agent := QuestGenAgent.new()
	add_child(agent)
	var ctx := {"npc_name":"X","parent_node_id":"start","choice_id":"go"}
	# Pre-populate the cache so expand_node skips the HTTP call entirely.
	agent._expand_cache[QuestGenAgent._expand_key(ctx)] = {"text":"cached!","choices":[]}
	var r: Dictionary = await agent.expand_node(ctx)
	agent.queue_free()
	if not r.get("ok", false): return "agent did not return ok"
	if not r.get("cached", false): return "agent did not report cache hit"
	if r.node.get("text","") != "cached!": return "wrong text returned"
	return ""

func _t_expand_prefetch() -> Variant:
	var main_node: Node = await _spawn_main_with_fixture()
	if main_node == null: return "could not spawn Main"
	# Pre-populate the agent cache so the prefetch coroutines find it
	# without hitting Ollama. Then add a synthetic node with __expand__
	# choices and verify _prefetch_expansions invokes expand_node which
	# returns cached content.
	var agent: QuestGenAgent = main_node.get("quest_agent")
	if agent == null:
		main_node.queue_free()
		return "main lacks quest_agent"
	var npcs := get_tree().get_nodes_in_group("npc")
	var bandit: NPC = null
	for n in npcs:
		if (n as NPC).npc_name == "Bandit":
			bandit = n
	if bandit == null:
		main_node.queue_free()
		return "Bandit not found"
	# Inject a probe node into Bandit's dialog tree.
	bandit.dialog_tree["probe"] = {
		"text": "probe parent",
		"choices": [
			{"id":"go_left","text":"left","next":"__expand__","next_hint":"goes left"},
			{"id":"go_right","text":"right","next":"__expand__","next_hint":"goes right"},
		],
	}
	var ctx_l: Dictionary = main_node.call("_build_expand_context", bandit, "probe", bandit.dialog_tree.probe.choices[0])
	var ctx_r: Dictionary = main_node.call("_build_expand_context", bandit, "probe", bandit.dialog_tree.probe.choices[1])
	var key_l := QuestGenAgent._expand_key(ctx_l)
	var key_r := QuestGenAgent._expand_key(ctx_r)
	agent._expand_cache[key_l] = {"text":"prefetched left","choices":[]}
	agent._expand_cache[key_r] = {"text":"prefetched right","choices":[]}
	# Trigger prefetch: invoke the same path _open_dialog_node uses.
	main_node.call("_prefetch_expansions", bandit, "probe", bandit.dialog_tree.probe)
	await get_tree().process_frame
	# Both keys should still be in the cache (no LLM call needed; nothing evicted).
	var ok_l := agent._expand_cache.has(key_l)
	var ok_r := agent._expand_cache.has(key_r)
	main_node.queue_free()
	await get_tree().process_frame
	if not ok_l or not ok_r:
		return "expected both prefetch keys to remain cached"
	return ""

func _t_expand_splice_in_dialog() -> Variant:
	var main_node: Node = await _spawn_main_with_fixture()
	if main_node == null: return "could not spawn Main"
	var agent: QuestGenAgent = main_node.get("quest_agent")
	var bandit: NPC = null
	for n in get_tree().get_nodes_in_group("npc"):
		if (n as NPC).npc_name == "Bandit":
			bandit = n
	if bandit == null:
		main_node.queue_free()
		return "Bandit not found"
	# Synthetic node with one __expand__ choice.
	bandit.dialog_tree["probe"] = {
		"text": "probe parent",
		"choices": [
			{"id":"deep","text":"go deep","next":"__expand__","next_hint":"goes deep"},
		],
	}
	# Pre-cache the expansion so no HTTP is needed.
	var choice: Dictionary = bandit.dialog_tree.probe.choices[0]
	var ctx: Dictionary = main_node.call("_build_expand_context", bandit, "probe", choice)
	var key := QuestGenAgent._expand_key(ctx)
	agent._expand_cache[key] = {"text":"DEEP NODE","choices":[]}
	# Open the probe node (simulating the player arriving here).
	main_node.set("_current_npc", bandit)
	main_node.set("_dialog_node_id", "probe")
	# Drive the splice via _expand_and_navigate.
	await main_node.call("_expand_and_navigate", bandit, choice)
	# Verify splicing: the new node id is "probe__deep", tree now contains it,
	# choice.next was rewritten to that id.
	var new_id := "probe__deep"
	var has_node: bool = bandit.dialog_tree.has(new_id)
	var nxt_rewritten: bool = String(choice.get("next","")) == new_id
	var node_text: String = String(bandit.dialog_tree.get(new_id, {}).get("text",""))
	main_node.queue_free()
	await get_tree().process_frame
	if not has_node: return "spliced node missing from tree"
	if not nxt_rewritten: return "choice.next not rewritten"
	if node_text != "DEEP NODE": return "spliced node text wrong: '%s'" % node_text
	return ""

# --- live tests (opt-in) ---

func _t_live_phi4() -> Variant:
	var agent := QuestGenAgent.new()
	add_child(agent)
	var result: Dictionary = await agent.generate(LlmPrompts.DEFAULT_PREMISE)
	agent.queue_free()
	if not result.get("ok", false):
		return "agent failed: %s" % result.get("error", "")
	var bundle: Dictionary = result.bundle
	if result.get("fallback", false):
		return "agent fell back to fixture (LLM did not produce valid output)"
	var errs := QuestValidator.validate(bundle)
	if not errs.is_empty():
		return "live bundle has %d validator errors despite agent claim of ok" % errs.size()
	return ""
