extends Node

# Headless smoke test for the quest system. Spins up a fake player + npc
# index, drives QuestManager via the same signals/methods the live game
# uses, and asserts each branch + the fail path resolve correctly.
#
# Run with:
#   godot --headless --path . res://scenes/Test.tscn

var _passes := 0
var _fails := 0
var _failures: Array[String] = []

class FakePlayer extends Node:
	var inventory: Inventory = Inventory.new()

func _ready() -> void:
	print("=== quest system smoke tests ===")
	_run("primary path empty + branch=combat",         _branch_combat)
	_run("branch=persuade",                            _branch_persuade)
	_run("branch=bribe",                               _branch_bribe)
	_run("branch=trade_food",                          _branch_trade_food)
	_run("branch=intimidate",                          _branch_intimidate)
	_run("branch=mediate (spread tree)",               _branch_mediate)
	_run("branch=side_with_bandit",                    _branch_side_with_bandit)
	_run("fail: kill Elder without ally flag",         _fail_kill_elder)
	_run("inventory predicate >=2 matches",            _predicate_inv)
	_run("quest:status:branch matcher",                _predicate_quest_branch)
	_run("dialog: start node priority (first match)",  _dialog_start_priority)
	_run("dialog: start fallback when none match",     _dialog_start_fallback)
	_run("dialog: start gated by inventory",           _dialog_start_inventory)
	_run("dialog: choice gating filters list",         _dialog_choice_gating)
	_run("dialog: choice gated by inv:sword>=1",       _dialog_choice_inventory)
	_run("dialog: memory:NPC.k matcher",               _dialog_memory_match)
	print("=== %d passed, %d failed ===" % [_passes, _fails])
	if _fails > 0:
		for f in _failures:
			print(" FAIL: ", f)
	get_tree().quit(1 if _fails > 0 else 0)

func _run(name: String, fn: Callable) -> void:
	# Reset QuestManager between tests.
	QuestManager.active_quests.clear()
	QuestManager.completed_quests.clear()
	QuestManager.global_flags.clear()
	var fp := FakePlayer.new()
	add_child(fp)
	QuestManager.bind_player(fp)
	var ok := true
	var err := ""
	var result = fn.call(fp)
	if result is Dictionary and result.has("ok"):
		ok = result.ok
		err = result.get("err", "")
	else:
		ok = bool(result)
	if ok:
		_passes += 1
		print("  ok    %s" % name)
	else:
		_fails += 1
		_failures.append("%s — %s" % [name, err])
		print("  FAIL  %s — %s" % [name, err])
	fp.queue_free()

# --- helpers ---

func _seed_quest() -> Quest:
	var q := QuestManager.add_quest_from_dict(_quest_dict())
	return q

func _quest_dict() -> Dictionary:
	# Mirror of the live quest in main.gd. Kept inline so tests stay
	# decoupled from the level setup.
	return {
		"id": "stolen_heirloom",
		"title": "Heirloom",
		"sequential": false,
		"objectives": [],
		"rewards": [],
		"branches": [
			{"id":"combat","objectives":[
				{"type":"kill_npc","params":{"npc_name":"Bandit"},"required":1},
				{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1},
			],"rewards":[{"item_id":"coin_gold","count":5}]},
			{"id":"persuade","requires_flags":{"persuaded":"true"},"objectives":[
				{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1},
			],"rewards":[{"item_id":"coin_gold","count":5},{"item_id":"key_silver","count":1}]},
			{"id":"bribe","requires_flags":{"bribed":"true"},"objectives":[
				{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1},
			],"rewards":[{"item_id":"coin_gold","count":3}]},
			{"id":"side_with_bandit","requires_flags":{"bandit_ally":"true"},"objectives":[
				{"type":"kill_npc","params":{"npc_name":"Elder"},"required":1},
			],"rewards":[{"item_id":"axe","count":1}]},
			{"id":"trade_food","requires_flags":{"traded_food":"true"},"objectives":[
				{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1},
			],"rewards":[{"item_id":"coin_gold","count":4}]},
			{"id":"intimidate","requires_flags":{"intimidated":"true"},"objectives":[
				{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1},
			],"rewards":[{"item_id":"coin_gold","count":4}]},
			{"id":"mediate","requires_flags":{"mediated":"true"},"objectives":[
				{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1},
			],"rewards":[{"item_id":"coin_gold","count":8},{"item_id":"medipack","count":1}]},
		],
		"fail_conditions":[
			{"type":"kill_npc","params":{"npc_name":"Elder"},"required":1},
		],
	}

func _expect(q: Quest, want_status: int, want_branch: String) -> Dictionary:
	if q.status != want_status:
		return {"ok": false, "err": "status=%d want=%d" % [q.status, want_status]}
	if want_branch != "" and q.completed_branch_id != want_branch:
		return {"ok": false, "err": "branch=%s want=%s" % [q.completed_branch_id, want_branch]}
	return {"ok": true}

func _give_player(p: FakePlayer, id: String, n: int = 1) -> void:
	p.inventory.add(id, n)

# --- branch tests ---

func _branch_combat(p: FakePlayer) -> Dictionary:
	var q := _seed_quest()
	Game.npc_killed.emit("Bandit")
	Game.npc_interacted.emit("Elder", "give:gem_red")
	return _expect(q, Quest.Status.COMPLETED, "combat")

func _branch_persuade(p: FakePlayer) -> Dictionary:
	var q := _seed_quest()
	QuestManager.set_flag_all_active("persuaded", "true")
	Game.npc_interacted.emit("Elder", "give:gem_red")
	return _expect(q, Quest.Status.COMPLETED, "persuade")

func _branch_bribe(p: FakePlayer) -> Dictionary:
	var q := _seed_quest()
	QuestManager.set_flag_all_active("bribed", "true")
	Game.npc_interacted.emit("Elder", "give:gem_red")
	return _expect(q, Quest.Status.COMPLETED, "bribe")

func _branch_trade_food(p: FakePlayer) -> Dictionary:
	var q := _seed_quest()
	QuestManager.set_flag_all_active("traded_food", "true")
	Game.npc_interacted.emit("Elder", "give:gem_red")
	return _expect(q, Quest.Status.COMPLETED, "trade_food")

func _branch_intimidate(p: FakePlayer) -> Dictionary:
	var q := _seed_quest()
	QuestManager.set_flag_all_active("intimidated", "true")
	Game.npc_interacted.emit("Elder", "give:gem_red")
	return _expect(q, Quest.Status.COMPLETED, "intimidate")

func _branch_mediate(p: FakePlayer) -> Dictionary:
	var q := _seed_quest()
	# Simulate the full spread tree:
	#   1) Bandit shares backstory → bandit_sympathy
	#   2) Elder confronted → elder_confessed
	#   3) Tell bandit elder confessed → mediated, gives gem
	#   4) Return gem to Elder
	QuestManager.set_flag_all_active("bandit_sympathy", "true")
	QuestManager.set_flag_all_active("elder_confessed", "true")
	QuestManager.set_flag_all_active("mediated", "true")
	Game.npc_interacted.emit("Elder", "give:gem_red")
	return _expect(q, Quest.Status.COMPLETED, "mediate")

func _branch_side_with_bandit(p: FakePlayer) -> Dictionary:
	var q := _seed_quest()
	QuestManager.set_flag_all_active("bandit_ally", "true")
	Game.npc_killed.emit("Elder")
	# Branch is checked BEFORE fail_conditions, so this should win, not fail.
	return _expect(q, Quest.Status.COMPLETED, "side_with_bandit")

func _fail_kill_elder(p: FakePlayer) -> Dictionary:
	var q := _seed_quest()
	Game.npc_killed.emit("Elder")
	return _expect(q, Quest.Status.FAILED, "")

# --- predicate tests (state_match) ---

func _predicate_inv(p: FakePlayer) -> Dictionary:
	_give_player(p, "stone", 3)
	if not QuestManager.state_match({"inv:stone":">=2"}, p):
		return {"ok": false, "err": "inv:stone>=2 should match (have 3)"}
	if QuestManager.state_match({"inv:stone":">=4"}, p):
		return {"ok": false, "err": "inv:stone>=4 should NOT match"}
	if QuestManager.state_match({"inv:apple":">=1"}, p):
		return {"ok": false, "err": "inv:apple>=1 should NOT match (none)"}
	return {"ok": true}

# --- dialog tree helpers ---

# Build a stand-in NPC. We do NOT add_child it so _ready() never fires —
# this keeps the test free of sprite/collision setup.
func _mk_npc(name: String, dialog_tree: Dictionary, starts: Array, dialog_start: String = "start") -> NPC:
	var n := NPC.new()
	n.npc_name = name
	n.dialog_tree = dialog_tree
	n.start_nodes = starts
	n.dialog_start = dialog_start
	return n

# --- dialog tree tests ---

func _dialog_start_priority(p: FakePlayer) -> Dictionary:
	var npc := _mk_npc("X", {
		"start": {"text":"x","choices":[]},
		"start_done": {"text":"x","choices":[]},
		"start_active": {"text":"x","choices":[]},
	}, [
		{"node":"start_done",   "requires":{"flag:done":"true"}},
		{"node":"start_active", "requires":{"flag:active":"true"}},
		{"node":"start",        "requires":{}},
	], "start")
	QuestManager.global_flags["active"] = "true"
	var picked := npc.resolve_start_node(p, {})
	if picked != "start_active":
		return {"ok": false, "err": "got %s want start_active" % picked}
	# Now also set 'done' — earlier entry should win.
	QuestManager.global_flags["done"] = "true"
	picked = npc.resolve_start_node(p, {})
	if picked != "start_done":
		return {"ok": false, "err": "priority broken: got %s want start_done" % picked}
	npc.queue_free()
	return {"ok": true}

func _dialog_start_fallback(p: FakePlayer) -> Dictionary:
	var npc := _mk_npc("X", {
		"hello": {"text":"x","choices":[]},
	}, [
		{"node":"never", "requires":{"flag:never":"true"}},
	], "hello")
	var picked := npc.resolve_start_node(p, {})
	if picked != "hello":
		return {"ok": false, "err": "expected fallback to dialog_start, got %s" % picked}
	npc.queue_free()
	return {"ok": true}

func _dialog_start_inventory(p: FakePlayer) -> Dictionary:
	var npc := _mk_npc("X", {
		"start_armed": {"text":"x","choices":[]},
		"start": {"text":"x","choices":[]},
	}, [
		{"node":"start_armed", "requires":{"inv:sword":">=1"}},
		{"node":"start", "requires":{}},
	], "start")
	if npc.resolve_start_node(p, {}) != "start":
		return {"ok": false, "err": "unarmed should pick start"}
	_give_player(p, "sword", 1)
	if npc.resolve_start_node(p, {}) != "start_armed":
		return {"ok": false, "err": "armed should pick start_armed"}
	npc.queue_free()
	return {"ok": true}

func _dialog_choice_gating(p: FakePlayer) -> Dictionary:
	var npc := _mk_npc("X", {
		"n": {"text":"x","choices":[
			{"id":"a","text":"A","requires":{"flag:f1":"true"}},
			{"id":"b","text":"B","requires":{"flag:f2":"true"}},
			{"id":"c","text":"C"},   # always
		]},
	}, [], "n")
	var visible := npc.visible_choices("n", p, {})
	if visible.size() != 1 or visible[0].id != "c":
		return {"ok": false, "err": "expected only [c]; got %s" % str(visible)}
	QuestManager.global_flags["f1"] = "true"
	visible = npc.visible_choices("n", p, {})
	if visible.size() != 2:
		return {"ok": false, "err": "expected 2 visible after f1; got %d" % visible.size()}
	npc.queue_free()
	return {"ok": true}

func _dialog_choice_inventory(p: FakePlayer) -> Dictionary:
	var npc := _mk_npc("X", {
		"n": {"text":"x","choices":[
			{"id":"draw","text":"[draw blade]","requires":{"inv:sword":">=1"}},
		]},
	}, [], "n")
	if npc.visible_choices("n", p, {}).size() != 0:
		return {"ok": false, "err": "no sword: choice should be hidden"}
	_give_player(p, "sword", 1)
	if npc.visible_choices("n", p, {}).size() != 1:
		return {"ok": false, "err": "with sword: choice should be visible"}
	npc.queue_free()
	return {"ok": true}

func _dialog_memory_match(p: FakePlayer) -> Dictionary:
	var bandit := _mk_npc("Bandit", {
		"n": {"text":"x","choices":[
			{"id":"recall","text":"You said earlier...","requires":{"memory:Bandit.told":"yes"}},
		]},
	}, [], "n")
	var idx := {"Bandit": bandit}
	if bandit.visible_choices("n", p, idx).size() != 0:
		bandit.queue_free()
		return {"ok": false, "err": "memory unset: should be hidden"}
	bandit.memory["told"] = "yes"
	if bandit.visible_choices("n", p, idx).size() != 1:
		bandit.queue_free()
		return {"ok": false, "err": "memory set: should be visible"}
	bandit.queue_free()
	return {"ok": true}

func _predicate_quest_branch(p: FakePlayer) -> Dictionary:
	# Complete a quest on the persuade branch and assert the matcher recognises
	# both the bare 'completed' and the branch-specific 'completed:persuade' form.
	var q := _seed_quest()
	QuestManager.set_flag_all_active("persuaded", "true")
	Game.npc_interacted.emit("Elder", "give:gem_red")
	if q.status != Quest.Status.COMPLETED:
		return {"ok": false, "err": "quest did not complete"}
	if not QuestManager.state_match({"quest:stolen_heirloom":"completed"}, p):
		return {"ok": false, "err": "quest:stolen_heirloom=completed should match"}
	if not QuestManager.state_match({"quest:stolen_heirloom":"completed:persuade"}, p):
		return {"ok": false, "err": "completed:persuade should match"}
	if QuestManager.state_match({"quest:stolen_heirloom":"completed:combat"}, p):
		return {"ok": false, "err": "completed:combat should NOT match"}
	return {"ok": true}
