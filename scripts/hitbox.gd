class_name Hitbox
extends Area2D

@export var damage: int = 1
@export var team: String = "player"
@export var lifetime: float = 0.15
@export var source: Node = null

func _ready() -> void:
	collision_layer = 1 << 5  # Hitbox
	collision_mask = 1 << 6   # Hurtbox
	monitorable = true
	monitoring = true
	if lifetime > 0.0:
		var t := get_tree().create_timer(lifetime)
		t.timeout.connect(queue_free)

static func spawn(parent: Node, pos: Vector2, radius: float, dmg: int, team: String, source: Node) -> Hitbox:
	var h := Hitbox.new()
	h.damage = dmg
	h.team = team
	h.source = source
	h.position = pos
	var s := CollisionShape2D.new()
	var c := CircleShape2D.new()
	c.radius = radius
	s.shape = c
	h.add_child(s)
	parent.add_child(h)
	return h
