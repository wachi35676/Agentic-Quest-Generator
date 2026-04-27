class_name Quest
extends RefCounted

# Quest with branching paths to completion.
#
# A quest has:
#   - `objectives`: the "primary" path (used if no branches are defined or
#     none have been completed). May be sequential.
#   - `branches`: zero or more alternative completion paths. Each has its own
#     objective list and rewards. Quest completes the moment ANY branch (or
#     the primary path) is fully satisfied.
#   - `fail_conditions`: a flat list of "fail objectives" — if any reaches
#     `required`, the quest fails immediately with no rewards.
#   - `flags`: free-form Dictionary for narrative state (set by dialog
#     actions, checked by branch availability — see `available_branches`).
#   - per-branch `requires_flags`: optional Dictionary; the branch is only
#     active (accepts progress) when all required flags match.
#
# All of this is data-only. The LLM phase emits the same dict shape via
# `Quest.from_dict()`.

enum Status { ACTIVE, COMPLETED, FAILED }

class Branch extends RefCounted:
	var id: String = ""
	var description: String = ""
	var objectives: Array[Objective] = []
	var rewards: Array = []
	var requires_flags: Dictionary = {}

	static func from_dict(d: Dictionary) -> Branch:
		var b := Branch.new()
		b.id = d.get("id", "")
		b.description = d.get("description", "")
		b.rewards = d.get("rewards", [])
		b.requires_flags = d.get("requires_flags", {})
		b.objectives.clear()
		for od in d.get("objectives", []):
			b.objectives.append(Objective.from_dict(od))
		return b

	func to_dict() -> Dictionary:
		var out := {
			"id": id, "description": description,
			"rewards": rewards, "requires_flags": requires_flags,
			"objectives": [],
		}
		for o in objectives:
			out.objectives.append(o.to_dict())
		return out

	func is_complete() -> bool:
		if objectives.is_empty():
			return false
		for o in objectives:
			if not o.is_done():
				return false
		return true

var id: String = ""
var title: String = ""
var description: String = ""
var objectives: Array[Objective] = []
var rewards: Array = []
var sequential: bool = false
var branches: Array[Branch] = []
var fail_conditions: Array[Objective] = []
var flags: Dictionary = {}
var status: int = Status.ACTIVE
var completed_branch_id: String = ""   # "main" if primary path; else branch id
var failed_objective_summary: String = ""
# Free-form scratchpad. Used by the continuation system to count regens
# (`continuations` int) and remember the original bundle's NPC/item refs
# so each splice stays consistent with the world.
var meta: Dictionary = {}

static func from_dict(d: Dictionary) -> Quest:
	var q := Quest.new()
	q.id = d.get("id", "")
	q.title = d.get("title", "")
	q.description = d.get("description", "")
	q.sequential = bool(d.get("sequential", false))
	q.rewards = d.get("rewards", [])
	q.flags = d.get("flags", {}).duplicate(true)
	q.objectives.clear()
	for od in d.get("objectives", []):
		q.objectives.append(Objective.from_dict(od))
	q.branches.clear()
	for bd in d.get("branches", []):
		q.branches.append(Branch.from_dict(bd))
	q.fail_conditions.clear()
	for fd in d.get("fail_conditions", []):
		q.fail_conditions.append(Objective.from_dict(fd))
	return q

func to_dict() -> Dictionary:
	var out := {
		"id": id, "title": title, "description": description,
		"sequential": sequential, "rewards": rewards, "flags": flags,
		"status": status, "completed_branch_id": completed_branch_id,
		"objectives": [], "branches": [], "fail_conditions": [],
	}
	for o in objectives:
		out.objectives.append(o.to_dict())
	for b in branches:
		out.branches.append(b.to_dict())
	for o in fail_conditions:
		out.fail_conditions.append(o.to_dict())
	return out

# -- branch availability based on flags --

func flags_match(req: Dictionary) -> bool:
	for k in req.keys():
		if not flags.has(k) or flags[k] != req[k]:
			return false
	return true

func _flags_match(req: Dictionary) -> bool:
	return flags_match(req)

func available_branches() -> Array:
	var out: Array = []
	for b in branches:
		if _flags_match(b.requires_flags):
			out.append(b)
	return out

# -- which objectives currently accept events --

func active_primary_objectives() -> Array:
	if not sequential:
		return objectives
	for o in objectives:
		if not o.is_done():
			return [o]
	return []

func active_objectives_all() -> Array:
	# Every objective the manager should try to advance on each event.
	var arr: Array = []
	arr.append_array(active_primary_objectives())
	for b in available_branches():
		arr.append_array(b.objectives)
	arr.append_array(fail_conditions)
	return arr

func _primary_complete() -> bool:
	if objectives.is_empty():
		return false
	for o in objectives:
		if not o.is_done():
			return false
	return true

func evaluate() -> Dictionary:
	# Returns {state: "active"|"completed"|"failed", branch_id, rewards}.
	# Branches and the primary path are checked BEFORE fail conditions so a
	# branch whose flags happen to be set wins over a fail-trigger event
	# (e.g. side_with_bandit beats the kill-Elder fail).
	#
	# Orchestrator-managed quests (Wanderer-driven) DON'T self-terminate.
	# Closure happens only when the player talks to the Wanderer and the
	# LLM emits decision="complete". Until then, branches are advisory.
	if bool(meta.get("orchestrator_managed", false)):
		return {"state": "active"}
	for b in available_branches():
		if b.is_complete():
			return {"state": "completed", "branch_id": b.id, "rewards": b.rewards}
	if _primary_complete():
		return {"state": "completed", "branch_id": "main", "rewards": rewards}
	for o in fail_conditions:
		if o.is_done():
			failed_objective_summary = o.summary()
			return {"state": "failed"}
	return {"state": "active"}

func set_flag(key: String, value: Variant) -> void:
	flags[key] = value

func get_flag(key: String, default: Variant = null) -> Variant:
	return flags.get(key, default)
