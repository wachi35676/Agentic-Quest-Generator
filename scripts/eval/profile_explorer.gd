class_name ProfileExplorer
extends ScriptedPlayer

# Explorer: rotates through three actions — talk, give, kill — one per
# distinct NPC. Reports back to Wanderer between cycles.

enum Phase { TALK, GIVE, KILL, REPORT }

var _phase: int = Phase.TALK
var _used: Dictionary = {}    # npc_name -> last phase used

func _choose_action() -> void:
	if _phase == Phase.REPORT:
		_interact_with(wanderer)
		return
	var alive := _alive_llm_npcs()
	if alive.is_empty():
		_phase = Phase.REPORT
		return
	# Pick an NPC that hasn't been used for this phase yet.
	var target: Node = null
	for n in alive:
		if int(_used.get((n as NPC).npc_name, -1)) != _phase:
			target = n
			break
	if target == null:
		# Nothing fresh for this phase; advance.
		_phase = (_phase + 1) % 4
		return
	match _phase:
		Phase.TALK:
			if _move_toward(target, 14.0):
				_used[(target as NPC).npc_name] = Phase.TALK
				player.scripted_interact()
				_phase = Phase.GIVE
		Phase.GIVE:
			# Give phase: open the NPC, dialog autopilot will hit Give.
			if _move_toward(target, 14.0):
				_used[(target as NPC).npc_name] = Phase.GIVE
				player.scripted_interact()
				_phase = Phase.KILL
		Phase.KILL:
			_attack_target(target)
			if not is_instance_valid(target) or (target as NPC).health <= 0:
				_used[(target as NPC).npc_name] = Phase.KILL
				_phase = Phase.REPORT

func _drive_npc_dialog() -> void:
	var labels := _dialog_button_labels()
	# In GIVE phase, prefer the [Give] action so we trigger the inventory
	# picker (which the base class then auto-picks slot 0 for via the
	# item_chosen handler below).
	if _phase == Phase.GIVE and "Give" in labels:
		dialog.action_chosen.emit("Give")
		_last_progress_ms = Time.get_ticks_msec()
		return
	# Otherwise pick the first choice or close.
	var choices := _dialog_choices()
	if not choices.is_empty():
		dialog.choice_chosen.emit(choices[0])
		_last_progress_ms = Time.get_ticks_msec()
		return
	if "Bye" in labels:
		dialog.action_chosen.emit("Bye")
	else:
		dialog.close_dialog()

# Also auto-pick an inventory item when the picker shows up.
func _physics_process(delta: float) -> void:
	super(delta)
	if _ended: return
	if dialog != null and dialog.visible and "_dialog_state" in player.get_parent():
		# Inventory picker is shown when main._dialog_state == "give"/"take".
		var st: String = String(player.get_parent()._dialog_state)
		if st == "give" or st == "take":
			# Find first non-empty inventory slot.
			for i in player.inventory.SLOT_COUNT:
				if player.inventory.slots[i] != null:
					dialog.item_chosen.emit(i)
					_last_progress_ms = Time.get_ticks_msec()
					return
			# No items — close.
			dialog.close_dialog()
