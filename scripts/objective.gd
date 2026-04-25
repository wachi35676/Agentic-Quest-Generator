class_name Objective
extends RefCounted

# Reusable objective. The `type` string identifies which game event(s) advance
# this objective; `params` carries the type-specific filters; `progress` and
# `required` are the counters. The class is event-driven: QuestManager calls
# `try_advance(event_type, payload)` for each registered Game signal — this
# class decides whether the event matches.
#
# Supported types (matched against Game autoload signals):
#   collect     params={item_id}                        ← item_picked_up
#   drop        params={item_id}                        ← item_dropped
#   give        params={npc_name, item_id}              ← npc_interacted "give:<item>"
#   take        params={npc_name, item_id}              ← npc_interacted "take:<item>"
#   talk        params={npc_name}                       ← npc_interacted "talk"
#   kill_enemy  params={enemy_type}                     ← enemy_killed
#   kill_npc    params={npc_name}                       ← npc_killed
#   reach          params={x, y, radius}                ← polled by QuestManager from player pos
#   dialog_choice  params={npc_name, choice_id}         ← Game.dialog_choice
#
# `params` may use "*" / "any" / null to wildcard-match.

var type: String = ""
var params: Dictionary = {}
var description: String = ""
var required: int = 1
var progress: int = 0

static func from_dict(d: Dictionary) -> Objective:
	var o := Objective.new()
	o.type = d.get("type", "")
	o.params = d.get("params", {})
	o.description = d.get("description", "")
	o.required = int(d.get("required", 1))
	o.progress = int(d.get("progress", 0))
	return o

func to_dict() -> Dictionary:
	return {
		"type": type,
		"params": params,
		"description": description,
		"required": required,
		"progress": progress,
	}

func is_done() -> bool:
	return progress >= required

func _matches_param(key: String, actual: Variant) -> bool:
	if not params.has(key):
		return true
	var expected = params[key]
	if expected == null or expected == "*" or expected == "any":
		return true
	return expected == actual

# Returns true if this event advanced this objective.
func try_advance(event_type: String, payload: Dictionary) -> bool:
	if is_done():
		return false
	var matched := false
	match type:
		"collect":
			if event_type == "item_picked_up" and _matches_param("item_id", payload.get("item_id")):
				progress += int(payload.get("count", 1))
				matched = true
		"drop":
			if event_type == "item_dropped" and _matches_param("item_id", payload.get("item_id")):
				progress += int(payload.get("count", 1))
				matched = true
		"give":
			if event_type == "npc_give" \
				and _matches_param("npc_name", payload.get("npc_name")) \
				and _matches_param("item_id", payload.get("item_id")):
				progress += 1
				matched = true
		"take":
			if event_type == "npc_take" \
				and _matches_param("npc_name", payload.get("npc_name")) \
				and _matches_param("item_id", payload.get("item_id")):
				progress += 1
				matched = true
		"talk":
			if event_type == "npc_talk" and _matches_param("npc_name", payload.get("npc_name")):
				progress += 1
				matched = true
		"kill_enemy":
			if event_type == "enemy_killed" and _matches_param("enemy_type", payload.get("enemy_type")):
				progress += 1
				matched = true
		"kill_npc":
			if event_type == "npc_killed" and _matches_param("npc_name", payload.get("npc_name")):
				progress += 1
				matched = true
		"dialog_choice":
			if event_type == "dialog_choice" \
				and _matches_param("npc_name", payload.get("npc_name")) \
				and _matches_param("choice_id", payload.get("choice_id")):
				progress += 1
				matched = true
		"reach":
			if event_type == "player_position":
				var px: float = payload.get("x", 0.0)
				var py: float = payload.get("y", 0.0)
				var tx: float = float(params.get("x", 0))
				var ty: float = float(params.get("y", 0))
				var r: float = float(params.get("radius", 16))
				if Vector2(px - tx, py - ty).length() <= r:
					progress = required
					matched = true
	if progress > required:
		progress = required
	return matched

func summary() -> String:
	if description != "":
		return "%s  (%d/%d)" % [description, progress, required]
	return "%s %s  (%d/%d)" % [type, JSON.stringify(params), progress, required]
