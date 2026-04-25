class_name Chest
extends StaticBody2D

@export var contents: Array = []   # array of {id, count}
@export var npc_name: String = "Chest"

var inventory: Inventory = Inventory.new()
var dialog_lines: Array[String] = ["A wooden chest."]

func _ready() -> void:
	add_to_group("npc")           # reuse the NPC interaction path in Main
	add_to_group("chest")
	collision_layer = 1 << 2
	collision_mask = 0
	for entry in contents:
		inventory.add(entry.id, entry.get("count", 1))
	var sprite := Sprite2D.new()
	var path := "res://assets/items/chest.png"
	if ResourceLoader.exists(path):
		sprite.texture = load(path)
	sprite.position = Vector2(0, -8)
	add_child(sprite)
	var s := CollisionShape2D.new()
	var r := RectangleShape2D.new()
	r.size = Vector2(14, 10)
	s.shape = r
	s.position = Vector2(0, -4)
	add_child(s)
