extends Node

# Headless session driver. Runs as the main scene when AGQ_PROFILE is
# set. Sequence:
#   1. Load Main.tscn as a sub-scene.
#   2. Wait for Main.world_ready (player + Wanderer + spawned NPCs ready).
#   3. Pick the right ScriptedPlayer subclass by AGQ_PROFILE env var.
#   4. inject() it with handles to player / level_root / dialog / Wanderer.
#   5. The scripted player drives gameplay until it self-quits or the
#      hard wall-clock timer fires.

const MAIN_SCENE := "res://scenes/Main.tscn"
const WALL_CLOCK_TIMEOUT_S := 360   # 6 min absolute kill switch

var _main_node: Node = null

func _ready() -> void:
	# Hard outer guard: if anything inside takes too long, kill the
	# process so a batch run isn't blocked by a hung session.
	get_tree().create_timer(WALL_CLOCK_TIMEOUT_S).timeout.connect(_on_outer_timeout)
	# Load Main as a child scene so its autoloads + autonomy still work.
	var packed: PackedScene = load(MAIN_SCENE)
	if packed == null:
		push_error("eval_session: cannot load Main.tscn")
		get_tree().quit(2)
		return
	_main_node = packed.instantiate()
	add_child(_main_node)
	# Wait for the world to fully populate.
	if _main_node.has_signal("world_ready"):
		await _main_node.world_ready
	else:
		# Old Main without the signal — give it a fixed delay.
		await get_tree().create_timer(1.0).timeout
	_attach_scripted_player()

func _attach_scripted_player() -> void:
	var profile := OS.get_environment("AGQ_PROFILE").to_lower()
	if profile == "": profile = "aggressive"
	# Direct field reads off Main are the most reliable way to grab
	# these — they're set during main._ready and named conventions vary.
	var player: Node = _main_node.player if "player" in _main_node else null
	var dialog: Node = _main_node.dialog if "dialog" in _main_node else null
	var level_root: Node = _main_node.level_root if "level_root" in _main_node else null
	var wanderer := _find_npc_named(_main_node, "Wanderer")
	if player == null or wanderer == null or dialog == null or level_root == null:
		push_error("eval_session: missing player=%s wanderer=%s dialog=%s level_root=%s" % [
				player, wanderer, dialog, level_root])
		get_tree().quit(3)
		return
	var sp: ScriptedPlayer
	match profile:
		"aggressive":     sp = ProfileAggressive.new()
		"cautious":       sp = ProfileCautious.new()
		"explorer":       sp = ProfileExplorer.new()
		"completionist":  sp = ProfileCompletionist.new()
		_:                sp = ProfileAggressive.new()
	sp.name = "ScriptedPlayer"
	add_child(sp)
	sp.inject(player, level_root, dialog, wanderer)
	print("[eval_session] attached profile=%s" % profile)

func _on_outer_timeout() -> void:
	EvaluationLogger.log("session_end", "eval_session", {
		"reason": "outer_wall_clock",
		"duration_ms": Time.get_ticks_msec() - EvaluationLogger.start_ms(),
	})
	EvaluationLogger.flush()
	get_tree().quit(0)

# --- node search helpers ---

func _find_descendant(root: Node, name: String) -> Node:
	if root.name == name: return root
	for c in root.get_children():
		var r := _find_descendant(c, name)
		if r != null: return r
	return null

func _find_descendant_by_class(root: Node, klass: String) -> Node:
	if root.get_class() == klass or (root.get_script() != null and root.get_script().get_global_name() == klass):
		return root
	for c in root.get_children():
		var r := _find_descendant_by_class(c, klass)
		if r != null: return r
	return null

func _find_npc_named(root: Node, npc_name: String) -> Node:
	if root is NPC and (root as NPC).npc_name == npc_name:
		return root
	for c in root.get_children():
		var r := _find_npc_named(c, npc_name)
		if r != null: return r
	return null
