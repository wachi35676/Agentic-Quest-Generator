extends Node

# Autoload. Owns active quests, listens to Game autoload signals, advances
# objectives, fires rewards on completion. The LLM phase will call
# `add_quest_from_dict(json_dict)` on this manager.

signal quest_added(quest: Quest)
signal quest_progress(quest: Quest, objective: Objective)
signal quest_completed(quest: Quest)
signal quest_failed(quest: Quest)

var active_quests: Array[Quest] = []
var completed_quests: Array[Quest] = []
# Story-significant player actions accumulated while a Wanderer-managed
# (orchestrator) quest is active. Each entry: { kind, params, frame }.
# Kept under cap so the orchestration prompt stays bounded.
const _LEDGER_CAP := 20
var action_ledger: Array = []

# Global narrative flags shared across all quests + dialog gating. Dialog
# `set_flag:k=v` writes here and onto every active quest's per-quest flags
# (so branch `requires_flags` continues to work without globals leaking).
var global_flags: Dictionary = {}

var _player: Node = null   # set externally for rewards

func _ready() -> void:
	Game.item_picked_up.connect(_on_item_picked_up)
	Game.item_dropped.connect(_on_item_dropped)
	Game.npc_interacted.connect(_on_npc_interacted)
	Game.npc_killed.connect(_on_npc_killed)
	Game.enemy_killed.connect(_on_enemy_killed)

func bind_player(p: Node) -> void:
	_player = p

# ---- public API ----

func add_quest(q: Quest) -> void:
	active_quests.append(q)
	quest_added.emit(q)

func add_quest_from_dict(d: Dictionary) -> Quest:
	var q := Quest.from_dict(d)
	add_quest(q)
	return q

func get_quest(id: String) -> Quest:
	for q in active_quests:
		if q.id == id:
			return q
	for q in completed_quests:
		if q.id == id:
			return q
	return null

# Call this from the level/main loop with the player's position so `reach`
# objectives can be evaluated.
func tick_player_position(pos: Vector2) -> void:
	_dispatch("player_position", {"x": pos.x, "y": pos.y})

# ---- signal handlers ----

func _on_item_picked_up(item_id: String, count: int) -> void:
	_dispatch("item_picked_up", {"item_id": item_id, "count": count})

func _on_item_dropped(item_id: String, count: int) -> void:
	_dispatch("item_dropped", {"item_id": item_id, "count": count})

func _on_npc_interacted(npc_name: String, action: String) -> void:
	if action == "talk":
		_dispatch("npc_talk", {"npc_name": npc_name})
	elif action.begins_with("give:"):
		var iid: String = action.substr(5)
		_dispatch("npc_give", {"npc_name": npc_name, "item_id": iid})
		record_action("npc_give", {"npc_name": npc_name, "item_id": iid})
	elif action.begins_with("take:"):
		var iid2: String = action.substr(5)
		_dispatch("npc_take", {"npc_name": npc_name, "item_id": iid2})
		record_action("npc_take", {"npc_name": npc_name, "item_id": iid2})

func _on_npc_killed(npc_name: String) -> void:
	_dispatch("npc_killed", {"npc_name": npc_name})
	record_action("kill_npc", {"npc_name": npc_name})

# Append a story-significant action to the ledger (capped at _LEDGER_CAP).
# Wanderer's orchestration prompt reads this list as the player's expressed
# creative intent — including unexpected actions, which the LLM is told to
# fold into new plot threads rather than fail the quest.
func record_action(kind: String, params: Dictionary) -> void:
	action_ledger.append({
		"kind": kind,
		"params": params,
		"frame": Engine.get_process_frames(),
	})
	if action_ledger.size() > _LEDGER_CAP:
		action_ledger = action_ledger.slice(action_ledger.size() - _LEDGER_CAP)

func clear_ledger() -> void:
	action_ledger.clear()

func _on_enemy_killed(enemy_type: String) -> void:
	_dispatch("enemy_killed", {"enemy_type": enemy_type})

# --- public: dialog/quest hooks the dialog system invokes ---

func dialog_choice(npc_name: String, choice_id: String) -> void:
	Game.dialog_choice.emit(npc_name, choice_id)
	_dispatch("dialog_choice", {"npc_name": npc_name, "choice_id": choice_id})
	record_action("dialog_choice", {"npc_name": npc_name, "choice_id": choice_id})

func set_quest_flag(quest_id: String, key: String, value: Variant) -> void:
	var q := get_quest(quest_id)
	if q != null:
		q.set_flag(key, value)
		# Re-check evaluation: a new flag may unlock a branch already done.
		_finalize_if_done(q)

func set_flag_all_active(key: String, value: Variant) -> void:
	# Convenience: dialog actions tag every active quest. Cheap because the
	# active set is small. Quest objectives can then read flags.
	global_flags[key] = value
	for q in active_quests:
		q.set_flag(key, value)
		_finalize_if_done(q)

func get_flag(key: String, default: Variant = null) -> Variant:
	return global_flags.get(key, default)

func flags_match(req: Dictionary) -> bool:
	for k in req.keys():
		if not global_flags.has(k) or global_flags[k] != req[k]:
			return false
	return true

# Rich predicate matcher used by dialog choice/start gating.
# Supported key prefixes:
#   "flag:KEY"     value any string  -> compare to global_flags[KEY]
#   "quest:ID"     value any of      -> compare quest status:
#                    "not_started" | "active" | "completed" | "failed"
#                  Optionally suffix with branch: "completed:branch_id"
#   "inv:item_id"  value e.g. ">=2", "==0", "0", "1" -> player inventory count
#   "memory:NPC.k" value any         -> per-NPC memory (set with remember:)
#   bare key       -> treated as flag:KEY (back-compat)
# Pass an empty dict to always match.
func state_match(req: Dictionary, player: Node = null, npcs_by_name: Dictionary = {}) -> bool:
	if req.is_empty():
		return true
	for raw_key in req.keys():
		# str() handles any Variant safely — String() on a dict/array
		# raises 'Nonexistent String constructor', which the LLM has
		# triggered by emitting nested objects in `requires`.
		var expected: String = str(req[raw_key])
		var key: String = str(raw_key)
		var prefix := ""
		var rest: String = key
		var ci := key.find(":")
		if ci > 0:
			prefix = key.substr(0, ci)
			rest = key.substr(ci + 1)
		match prefix:
			"flag", "":
				if global_flags.get(rest, "") != expected:
					return false
			"quest":
				var q: Quest = get_quest(rest)
				var actual: String = "not_started"
				if q != null:
					match q.status:
						Quest.Status.ACTIVE: actual = "active"
						Quest.Status.COMPLETED: actual = "completed"
						Quest.Status.FAILED: actual = "failed"
				# allow "completed:branch_id" form
				if ":" in expected:
					var pieces := expected.split(":", false, 1)
					if actual != pieces[0]: return false
					if q == null or q.completed_branch_id != pieces[1]: return false
				elif actual != expected:
					return false
			"inv":
				if player == null: return false
				var count: int = 0
				for s in player.inventory.slots:
					if s != null and s.id == rest:
						count += s.count
				if not _compare_int(count, expected):
					return false
			"memory":
				var dot := rest.find(".")
				if dot <= 0: return false
				var npc_name: String = rest.substr(0, dot)
				var k2: String = rest.substr(dot + 1)
				var npc = npcs_by_name.get(npc_name, null)
				if npc == null: return false
				if String(npc.memory.get(k2, "")) != expected:
					return false
			_:
				return false
	return true

func _compare_int(actual: int, spec: String) -> bool:
	if spec.begins_with(">="): return actual >= int(spec.substr(2))
	if spec.begins_with("<="): return actual <= int(spec.substr(2))
	if spec.begins_with("=="): return actual == int(spec.substr(2))
	if spec.begins_with(">"):  return actual >  int(spec.substr(1))
	if spec.begins_with("<"):  return actual <  int(spec.substr(1))
	return actual == int(spec)

# ---- core dispatch ----

func _dispatch(event_type: String, payload: Dictionary) -> void:
	var snapshot: Array = active_quests.duplicate()
	for q in snapshot:
		if q.status != Quest.Status.ACTIVE:
			continue
		var advanced := false
		for o in q.active_objectives_all():
			if o.try_advance(event_type, payload):
				advanced = true
				quest_progress.emit(q, o)
		if advanced:
			_finalize_if_done(q)

func _finalize_if_done(q: Quest) -> void:
	if q.status != Quest.Status.ACTIVE:
		return
	var ev: Dictionary = q.evaluate()
	if ev.state == "completed":
		_complete_quest(q, ev.get("branch_id", "main"), ev.get("rewards", []))
	elif ev.state == "failed":
		_fail_quest(q)

func _complete_quest(q: Quest, branch_id: String, rewards: Array) -> void:
	q.status = Quest.Status.COMPLETED
	q.completed_branch_id = branch_id
	active_quests.erase(q)
	completed_quests.append(q)
	_award_rewards(rewards)
	quest_completed.emit(q)
	Game.log_event("quest_completed", "%s [%s]" % [q.id, branch_id])

func _fail_quest(q: Quest) -> void:
	q.status = Quest.Status.FAILED
	active_quests.erase(q)
	completed_quests.append(q)
	quest_failed.emit(q)
	Game.log_event("quest_failed", q.id)

func _award_rewards(rewards: Array) -> void:
	if _player == null:
		return
	for r in rewards:
		var id: String = r.get("item_id", "")
		var n: int = int(r.get("count", 1))
		if id == "" or n <= 0:
			continue
		_player.inventory.add(id, n)
