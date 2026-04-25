extends Node

signal item_picked_up(item_id: String, count: int)
signal item_dropped(item_id: String, count: int)
signal npc_interacted(npc_name: String, action: String)
signal npc_killed(npc_name: String)
signal enemy_killed(enemy_type: String)
signal player_damaged(amount: int, current_health: int)
signal dialog_choice(npc_name: String, choice_id: String)

func log_event(tag: String, data: Variant = null) -> void:
	print("[event] %s %s" % [tag, str(data) if data != null else ""])
