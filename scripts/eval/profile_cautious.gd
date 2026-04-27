class_name ProfileCautious
extends ScriptedPlayer

# Cautious: visit each LLM-spawned NPC once, pick the first non-end
# dialog choice, then move on. Never attacks. Reports when every NPC
# has been visited.

var _visited: Dictionary = {}    # npc_name -> true

func _choose_action() -> void:
	var unvisited: Array = []
	for n in _alive_llm_npcs():
		if not _visited.has((n as NPC).npc_name):
			unvisited.append(n)
	if unvisited.is_empty():
		_interact_with(wanderer)
		return
	var target := _nearest(unvisited)
	# Mark visited as soon as we initiate interact — even if dialog
	# fails to open, we don't want to loop forever on a stuck NPC.
	if _move_toward(target, 14.0):
		_visited[(target as NPC).npc_name] = true
		player.scripted_interact()
		_last_progress_ms = Time.get_ticks_msec()

func _drive_npc_dialog() -> void:
	# Always pick the first available choice (whatever it is), then close
	# the next time the dialog opens by hitting Bye.
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
