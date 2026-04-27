class_name ProfileAggressive
extends ScriptedPlayer

# Aggressive: kill the nearest LLM-spawned NPC, then walk back to the
# Wanderer. Repeat. Never talks beyond required dialog autopilot.

func _choose_action() -> void:
	var alive := _alive_llm_npcs()
	if alive.is_empty():
		# Nothing left to kill — go report. Wanderer dialog autopilot
		# handles Yes/Report/Accept.
		_interact_with(wanderer)
		return
	var target := _nearest(alive)
	# Get into melee range, then swing.
	_attack_target(target)
