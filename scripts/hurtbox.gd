class_name Hurtbox
extends Area2D

signal hit(damage: int, source: Node)

@export var owner_team: String = "neutral"  # "player","npc","enemy"

func _ready() -> void:
	collision_layer = 1 << 6   # Hurtbox
	collision_mask = 1 << 5    # detect Hitboxes
	monitorable = true
	monitoring = true
	area_entered.connect(_on_area_entered)

func _on_area_entered(area: Area2D) -> void:
	if area is Hitbox:
		var hb := area as Hitbox
		if hb.team == owner_team:
			return
		hit.emit(hb.damage, hb.source)
