class_name ProfileCompletionist
extends ScriptedPlayer

# Completionist: visit every spawned NPC at least once, talk through
# two depth levels of dialog where possible, then kill ONE specific
# NPC matching role 'villain' (or first available), then report.

var _talked: Dictionary = {}      # npc_name -> dialog_visits
var _killed_one: bool = false

func _choose_action() -> void:
	# Phase 1: talk to everyone at least twice.
	var alive := _alive_llm_npcs()
	for n in alive:
		var nm: String = (n as NPC).npc_name
		if int(_talked.get(nm, 0)) < 2:
			if _move_toward(n, 14.0):
				_talked[nm] = int(_talked.get(nm, 0)) + 1
				player.scripted_interact()
			return
	# Phase 2: pick the villain (or first NPC) and kill them.
	if not _killed_one and not alive.is_empty():
		var villain: Node = null
		for n in alive:
			if String((n as NPC).role).to_lower().contains("vill") \
					or String((n as NPC).role).to_lower().contains("betr"):
				villain = n; break
		if villain == null: villain = alive[0]
		_attack_target(villain)
		if not is_instance_valid(villain) or (villain as NPC).health <= 0:
			_killed_one = true
		return
	# Phase 3: report.
	_interact_with(wanderer)
