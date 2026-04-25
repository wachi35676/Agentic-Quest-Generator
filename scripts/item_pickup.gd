class_name ItemPickup
extends Area2D

const PICKUP_GROUP := "pickup"

@export var item_id: String = "stone"
@export var count: int = 1

var _sprite: Sprite2D
var _shape: CollisionShape2D

func _ready() -> void:
	add_to_group(PICKUP_GROUP)
	collision_layer = 1 << 4   # Pickup
	collision_mask = 0
	monitoring = false
	monitorable = true
	_sprite = Sprite2D.new()
	_sprite.texture = ItemDB.get_texture(item_id)
	_sprite.centered = true
	add_child(_sprite)
	_shape = CollisionShape2D.new()
	var c := CircleShape2D.new()
	c.radius = 6.0
	_shape.shape = c
	add_child(_shape)
	_bob()

func _bob() -> void:
	var tween := create_tween().set_loops()
	tween.tween_property(_sprite, "position:y", -2.0, 0.6).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	tween.tween_property(_sprite, "position:y", 0.0, 0.6).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)

static func spawn(parent: Node, id: String, count: int, pos: Vector2) -> ItemPickup:
	var p := ItemPickup.new()
	p.item_id = id
	p.count = count
	p.position = pos
	parent.add_child(p)
	return p
