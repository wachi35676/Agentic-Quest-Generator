extends Node

# End-to-end playthrough tests. For each branch we:
#   1. Boot a fresh Main.tscn (real Player, NPCs, dialog UI, quest manager)
#   2. Drive the game with the SAME signals/methods the human player triggers
#      (interact -> dialog node -> choice button -> action -> next node)
#   3. Assert the live Quest object reaches the right Status + branch id.
#
# Run: godot --headless --path . res://scenes/TestPlay.tscn

const STEP_TIMEOUT := 4.0

var _main: Node
var _player: Player
var _bandit: NPC
var _elder: NPC
var _dialog: DialogBox

var _passes := 0
var _fails := 0
var _failures: Array[String] = []

func _ready() -> void:
	# Wait one frame so SceneTree finishes setting up *us* before we attach Main.
	await get_tree().process_frame
	print("=== playthrough tests ===")
	await _run("combat",            _play_combat)
	await _run("persuade",          _play_persuade)
	await _run("bribe",             _play_bribe)
	await _run("trade_food",        _play_trade_food)
	await _run("intimidate",        _play_intimidate)
	await _run("side_with_bandit",  _play_side_with_bandit)
	await _run("mediate (spread)",  _play_mediate)
	await _run("FAIL kill_elder",   _play_fail_kill_elder)
	print("=== %d passed, %d failed ===" % [_passes, _fails])
	for f in _failures:
		print(" FAIL: ", f)
	get_tree().quit(1 if _fails > 0 else 0)

# ---------- runner ----------

func _run(name: String, fn: Callable) -> void:
	if not await _setup_scene():
		_record(false, name, "scene refs missing")
		return
	var err: String = await fn.call()
	if err == "":
		_record(true, name, "")
	else:
		_record(false, name, err)
	await _teardown_scene()

func _record(ok: bool, name: String, err: String) -> void:
	if ok:
		_passes += 1
		print("  ok    ", name)
	else:
		_fails += 1
		_failures.append("%s — %s" % [name, err])
		print("  FAIL  %s — %s" % [name, err])

func _setup_scene() -> bool:
	# Reset autoload state.
	QuestManager.active_quests.clear()
	QuestManager.completed_quests.clear()
	QuestManager.global_flags.clear()
	var packed: PackedScene = load("res://scenes/Main.tscn")
	_main = packed.instantiate()
	get_tree().root.add_child(_main)
	await get_tree().process_frame
	await get_tree().process_frame
	return _grab_refs()

func _teardown_scene() -> void:
	if _main and is_instance_valid(_main):
		_main.queue_free()
	await get_tree().process_frame
	_main = null
	_player = null
	_bandit = null
	_elder = null
	_dialog = null

func _grab_refs() -> bool:
	for n in get_tree().get_nodes_in_group("player"):
		_player = n
	for n in get_tree().get_nodes_in_group("npc"):
		var npc := n as NPC
		if npc == null: continue
		if npc.npc_name == "Bandit": _bandit = npc
		elif npc.npc_name == "Elder": _elder = npc
	for c in _main.get_children():
		if c is DialogBox:
			_dialog = c
			break
	return _player != null and _bandit != null and _elder != null and _dialog != null

# ---------- DSL ----------
# Helpers chosen so each test reads as a chronological sequence of player
# actions. Errors bubble up as non-empty strings; tests `return await ...`
# the assertion functions to short-circuit.

func _interact(npc: NPC) -> String:
	if _dialog.visible: _dialog.close_dialog()
	_player.global_position = npc.global_position + Vector2(0, -20)
	_main.call("_on_player_interact", npc)
	if not await _wait_dialog_open():
		return "dialog did not open with %s" % npc.npc_name
	return ""

func _wait_dialog_open() -> bool:
	var t := 0.0
	while not _dialog.visible and t < STEP_TIMEOUT:
		await get_tree().process_frame
		t += 0.016
	return _dialog.visible

func _wait_dialog_closed() -> bool:
	var t := 0.0
	while _dialog.visible and t < STEP_TIMEOUT:
		await get_tree().process_frame
		t += 0.016
	return not _dialog.visible

func _choice(choice_id: String) -> String:
	var npc: Node = _main.get("_current_npc")
	var node_id: String = String(_main.get("_dialog_node_id"))
	if npc == null or node_id == "":
		return "no active dialog node"
	if not (npc is NPC):
		return "active target is not an NPC"
	var node: Dictionary = (npc as NPC).dialog_tree.get(node_id, {})
	for c in node.get("choices", []):
		if String(c.get("id","")) == choice_id:
			# Make sure the choice is actually visible (i.e. its requires pass).
			var idx: Dictionary = _main.call("_npc_index")
			var visible: Array = (npc as NPC).visible_choices(node_id, _player, idx)
			var seen := false
			for vc in visible:
				if String(vc.get("id","")) == choice_id:
					seen = true; break
			if not seen:
				return "choice %s exists but is gated out at node %s" % [choice_id, node_id]
			_dialog.choice_chosen.emit(c)
			await get_tree().process_frame
			return ""
	return "choice id %s not found at node %s" % [choice_id, node_id]

func _continue() -> String:
	# Click the auto-Continue button on a leaf node.
	for b in _all_buttons(_dialog):
		if b is Button and (b as Button).text == "Continue":
			(b as Button).emit_signal("pressed")
			await get_tree().process_frame
			return ""
	# Fall back: just close.
	_dialog.close_dialog()
	await get_tree().process_frame
	return ""

func _all_buttons(n: Node, out: Array = []) -> Array:
	for c in n.get_children():
		if c is Button: out.append(c)
		_all_buttons(c, out)
	return out

func _kill(npc: NPC) -> void:
	npc._die()

func _grant(item_id: String, n: int = 1) -> void:
	_player.inventory.add(item_id, n)

func _expect_complete(branch: String) -> String:
	var q := QuestManager.get_quest("stolen_heirloom")
	if q == null: return "quest missing"
	if q.status != Quest.Status.COMPLETED:
		return "quest not COMPLETED (status=%d)" % q.status
	if q.completed_branch_id != branch:
		return "wrong branch: %s want %s" % [q.completed_branch_id, branch]
	return ""

func _expect_failed() -> String:
	var q := QuestManager.get_quest("stolen_heirloom")
	if q == null: return "quest missing"
	if q.status != Quest.Status.FAILED:
		return "quest not FAILED (status=%d)" % q.status
	return ""

# ---------- branch playthroughs ----------

func _play_combat() -> String:
	# 1. Brief Elder so dialog is meaningful (and to set elder_briefed
	#    just like the real flow would).
	var e := await _interact(_elder); if e != "": return e
	e = await _choice("accept"); if e != "": return e
	await _continue()
	# 2. Kill Bandit (drops loot including gem_red); pick up gem manually.
	_kill(_bandit)
	_grant("gem_red", 1)
	# 3. Hand to Elder.
	e = await _interact(_elder); if e != "": return e
	e = await _choice("hand_gem"); if e != "": return e
	return _expect_complete("combat")

func _play_persuade() -> String:
	var e := await _interact(_elder); if e != "": return e
	e = await _choice("accept"); if e != "": return e
	await _continue()
	e = await _interact(_bandit); if e != "": return e
	e = await _choice("ask_gem"); if e != "": return e
	e = await _choice("persuade_honest"); if e != "": return e
	await _continue()
	e = await _interact(_elder); if e != "": return e
	e = await _choice("hand_gem"); if e != "": return e
	return _expect_complete("persuade")

func _play_bribe() -> String:
	_grant("coin_gold", 1)
	var e := await _interact(_elder); if e != "": return e
	e = await _choice("accept"); if e != "": return e
	await _continue()
	e = await _interact(_bandit); if e != "": return e
	e = await _choice("ask_gem"); if e != "": return e
	e = await _choice("persuade_bribe"); if e != "": return e
	await _continue()
	e = await _interact(_elder); if e != "": return e
	e = await _choice("hand_gem"); if e != "": return e
	return _expect_complete("bribe")

func _play_trade_food() -> String:
	_grant("fish", 1)
	var e := await _interact(_elder); if e != "": return e
	e = await _choice("accept"); if e != "": return e
	await _continue()
	e = await _interact(_bandit); if e != "": return e
	e = await _choice("ask_gem"); if e != "": return e
	e = await _choice("trade_fish"); if e != "": return e
	await _continue()
	e = await _interact(_elder); if e != "": return e
	e = await _choice("hand_gem"); if e != "": return e
	return _expect_complete("trade_food")

func _play_intimidate() -> String:
	_grant("sword", 1)
	var e := await _interact(_elder); if e != "": return e
	e = await _choice("accept"); if e != "": return e
	await _continue()
	e = await _interact(_bandit); if e != "": return e
	e = await _choice("ask_gem"); if e != "": return e
	e = await _choice("threaten_sword"); if e != "": return e
	await _continue()
	e = await _interact(_elder); if e != "": return e
	e = await _choice("hand_gem"); if e != "": return e
	return _expect_complete("intimidate")

func _play_side_with_bandit() -> String:
	var e := await _interact(_elder); if e != "": return e
	e = await _choice("accept"); if e != "": return e
	await _continue()
	e = await _interact(_bandit); if e != "": return e
	e = await _choice("ally_offer"); if e != "": return e
	e = await _choice("ally_accept"); if e != "": return e
	await _continue()
	# Now eliminate the elder. Dialog is closed; just _die().
	_kill(_elder)
	return _expect_complete("side_with_bandit")

func _play_mediate() -> String:
	# 1. Brief Elder.
	var e := await _interact(_elder); if e != "": return e
	e = await _choice("accept"); if e != "": return e
	await _continue()
	# 2. Hear Bandit's backstory → bandit_sympathy=true.
	e = await _interact(_bandit); if e != "": return e
	e = await _choice("why_take"); if e != "": return e
	e = await _choice("believe"); if e != "": return e
	# Backstory_after → choose to leave (close).
	# The "back" path goes via "ask_gem2" → "ask" but we don't want to ask
	# yet. Just close the dialog.
	_dialog.close_dialog()
	if not await _wait_dialog_closed(): return "bandit dialog stuck open"
	# 3. Confront Elder with the truth → elder_confessed=true.
	e = await _interact(_elder); if e != "": return e
	e = await _choice("confront"); if e != "": return e
	e = await _choice("will_mediate"); if e != "": return e
	await _continue()
	# 4. Bring the truth back to Bandit → mediated=true, gem given.
	e = await _interact(_bandit); if e != "": return e
	e = await _choice("ask_gem"); if e != "": return e
	e = await _choice("deliver_truth"); if e != "": return e
	await _continue()
	# 5. Return gem to Elder → completes via mediate branch.
	e = await _interact(_elder); if e != "": return e
	e = await _choice("hand_gem"); if e != "": return e
	return _expect_complete("mediate")

func _play_fail_kill_elder() -> String:
	# Brief, then murder the Elder without striking the bandit-ally pact.
	var e := await _interact(_elder); if e != "": return e
	e = await _choice("accept"); if e != "": return e
	await _continue()
	_kill(_elder)
	return _expect_failed()
