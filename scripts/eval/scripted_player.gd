class_name ScriptedPlayer
extends Node

# Base class for the four eval profiles. Drives the player + dialog
# without real input. Subclasses override `_choose_action()` to decide
# what the player should do next (move toward an NPC, attack, talk).
# Dialog buttons are clicked by emitting the dialog's signals directly.
#
# Lifecycle:
#   1. eval_session.gd instantiates the right subclass after world_ready
#   2. inject(player, level_root, dialog, wanderer) is called
#   3. _physics_process drives the state machine
#   4. when done (chapter cap, stuck timeout, or external timeout), the
#      driver emits Game.session_end (signal added in this commit) and
#      eval_session.gd quits.

const TICK_INTERVAL := 0.4
const MAX_WALL_CLOCK_MS := 5 * 60 * 1000     # 5 min hard cap per session
const MAX_CHAPTERS := 4                       # walk to giver this many times max
const STUCK_TIMEOUT_MS := 30 * 1000           # if no progress in 30s, end session

var player: Node = null
var level_root: Node = null
var dialog: Node = null
var wanderer: Node = null

var _last_progress_ms: int = 0
var _start_ms: int = 0
var _tick_accum: float = 0.0
var _orchestrations_seen: int = 0
var _ended: bool = false

func inject(p: Node, lr: Node, d: Node, w: Node) -> void:
	player = p
	level_root = lr
	dialog = d
	wanderer = w
	_start_ms = Time.get_ticks_msec()
	_last_progress_ms = _start_ms
	# Listen for orchestrator events so we know when a new chapter
	# spawned (= time to act again).
	if QuestManager.has_signal("quest_completed"):
		QuestManager.quest_completed.connect(_on_quest_completed)
	if QuestManager.has_signal("quest_added"):
		QuestManager.quest_added.connect(_on_quest_added)

func _physics_process(delta: float) -> void:
	if _ended: return
	if player == null:
		# inject() hasn't run yet on the very first frame after add_child.
		return
	if Time.get_ticks_msec() - _start_ms >= MAX_WALL_CLOCK_MS:
		_end_session("wall_clock_timeout")
		return
	if Time.get_ticks_msec() - _last_progress_ms >= STUCK_TIMEOUT_MS:
		_end_session("stuck")
		return
	# Drive any open dialog first; it blocks gameplay otherwise.
	if dialog != null and dialog.visible:
		_drive_dialog()
		return
	# Throttle action ticks so we don't spam attacks/interacts.
	_tick_accum += delta
	if _tick_accum < TICK_INTERVAL:
		return
	_tick_accum = 0.0
	_choose_action()

# Override in subclasses.
func _choose_action() -> void:
	pass

# --- shared helpers ---

func _all_llm_npcs() -> Array:
	var out: Array = []
	for child in level_root.get_children():
		if child is NPC and not (child as NPC).has_meta("quest_giver_kind"):
			out.append(child)
	return out

func _alive_llm_npcs() -> Array:
	var out: Array = []
	for n in _all_llm_npcs():
		if is_instance_valid(n) and (n as NPC).health > 0:
			out.append(n)
	return out

func _nearest(npcs: Array) -> Node:
	var best: Node = null
	var best_d: float = INF
	for n in npcs:
		var d: float = (n.global_position - player.global_position).length()
		if d < best_d:
			best_d = d
			best = n
	return best

var _last_player_pos: Vector2 = Vector2.ZERO
var _stuck_ms: int = 0
var _sidestep_until: int = 0
var _sidestep_dir: Vector2 = Vector2.ZERO

func _move_toward(target: Node, stop_dist: float = 18.0) -> bool:
	# Returns true when arrived (distance < stop_dist).
	if target == null or not is_instance_valid(target):
		player.scripted_clear()
		return true
	var delta_v: Vector2 = target.global_position - player.global_position
	if delta_v.length() <= stop_dist:
		player.scripted_clear()
		return true
	# Stuck-detector: if the player hasn't moved >4 px since the last
	# tick, we're wedged on a wall. Pick a perpendicular sidestep
	# direction and commit to it for ~0.8s before re-aiming.
	var moved: float = (player.global_position - _last_player_pos).length()
	_last_player_pos = player.global_position
	if moved < 4.0:
		_stuck_ms += int(TICK_INTERVAL * 1000)
	else:
		_stuck_ms = 0
		_sidestep_until = 0
	if _stuck_ms >= 800 and Time.get_ticks_msec() >= _sidestep_until:
		# Choose perpendicular CCW (or CW on alternation).
		var perp: Vector2 = Vector2(-delta_v.y, delta_v.x).normalized()
		if randf() < 0.5: perp = -perp
		_sidestep_dir = perp
		_sidestep_until = Time.get_ticks_msec() + 800
	var dir: Vector2
	if Time.get_ticks_msec() < _sidestep_until:
		# Mix sidestep (0.7) + forward (0.3) so we slide along the wall.
		dir = (_sidestep_dir * 0.7 + delta_v.normalized() * 0.3).normalized()
	else:
		dir = delta_v.normalized()
	player.scripted_set_velocity(dir)
	_last_progress_ms = Time.get_ticks_msec()
	return false

func _interact_with(target: Node) -> void:
	# Walk close enough that _try_interact picks them up, then hit interact.
	if _move_toward(target, 14.0):
		player.scripted_interact()
		_last_progress_ms = Time.get_ticks_msec()

func _attack_target(target: Node) -> void:
	if not is_instance_valid(target): return
	if _move_toward(target, 14.0):
		player.scripted_attack()
		_last_progress_ms = Time.get_ticks_msec()

# --- dialog autopilot ---

# Click order priority. First match wins.
const _WANDERER_BUTTON_PRIORITY := [
	"Yes", "Report", "Accept", "Bye",
]
const _NPC_BUTTON_PRIORITY := [
	"Bye",   # default close — overridden by subclasses that want to pick choices
]

func _drive_dialog() -> void:
	# Whose dialog is this? main.gd sets dialog title to npc.npc_name.
	var title := _dialog_title()
	if wanderer != null and title == (wanderer as NPC).npc_name:
		_drive_wanderer_dialog()
	else:
		_drive_npc_dialog()

func _drive_wanderer_dialog() -> void:
	var labels := _dialog_button_labels()
	for prio in _WANDERER_BUTTON_PRIORITY:
		if prio in labels:
			dialog.action_chosen.emit(prio)
			_last_progress_ms = Time.get_ticks_msec()
			return
	# Nothing recognised — close.
	dialog.close_dialog()

# Subclasses override to pick choices instead of just Bye.
func _drive_npc_dialog() -> void:
	# Default: pick the first non-action choice if present, else Bye.
	var choices := _dialog_choices()
	if not choices.is_empty():
		dialog.choice_chosen.emit(choices[0])
		_last_progress_ms = Time.get_ticks_msec()
		return
	var labels := _dialog_button_labels()
	if "Bye" in labels:
		dialog.action_chosen.emit("Bye")
	else:
		dialog.close_dialog()

# --- dialog introspection ---

func _dialog_title() -> String:
	if dialog == null: return ""
	if "_title" in dialog and dialog._title != null:
		return String(dialog._title.text)
	return ""

func _dialog_button_labels() -> Array:
	var out: Array = []
	if dialog == null or not ("_buttons" in dialog) or dialog._buttons == null:
		return out
	for btn in dialog._buttons.get_children():
		if btn is Button:
			# Buttons are rendered as "[Label]" for action verbs; strip brackets.
			var t: String = String((btn as Button).text)
			if t.begins_with("[") and t.ends_with("]"):
				t = t.substr(1, t.length() - 2)
			out.append(t)
	return out

# Returns choice dicts (not button labels) when the dialog is showing a
# tree node. Empty otherwise.
func _dialog_choices() -> Array:
	# We can't recover the choice dicts from buttons cleanly, but main.gd
	# stores the active node id via _dialog_node_id. Walk current_npc's
	# dialog_tree[node].choices.
	var main := player.get_parent()
	if main == null or not ("_current_npc" in main) or main._current_npc == null:
		return []
	if not (main._current_npc is NPC): return []
	var npc: NPC = main._current_npc
	var nid: String = String(main._dialog_node_id)
	if nid == "" or not npc.dialog_tree.has(nid):
		return []
	return npc.visible_choices(nid, player, _empty_npc_index())

func _empty_npc_index() -> Dictionary:
	# Predicates referencing memory:NPC.field need an index; for our use
	# (default choice picking) an empty dict is fine.
	return {}

# --- session end ---

func _end_session(reason: String) -> void:
	if _ended: return
	_ended = true
	EvaluationLogger.log("session_end", "ScriptedPlayer", {
		"reason": reason,
		"orchestrations_seen": _orchestrations_seen,
		"duration_ms": Time.get_ticks_msec() - _start_ms,
		"profile": EvaluationLogger.profile(),
	})
	EvaluationLogger.flush()
	get_tree().quit(0)

# --- signal handlers ---

func _on_quest_added(_q) -> void:
	_last_progress_ms = Time.get_ticks_msec()
	_orchestrations_seen += 1
	if _orchestrations_seen >= MAX_CHAPTERS + 1:
		# +1 because the first quest_added is the kickoff, not an orchestration.
		_end_session("max_chapters_reached")

func _on_quest_completed(q) -> void:
	# If the orchestrator closed the quest, the session is over.
	var bid: String = String(q.completed_branch_id)
	if bid == "orchestrator_closing":
		_end_session("orchestrator_closing")
