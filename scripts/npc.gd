class_name NPC
extends CharacterBody2D

@export var npc_name: String = "Villager"
@export var character_sheet: String = "Villager"   # folder under assets/characters/
@export var role: String = "villager"
@export var max_health: int = 3
@export var initial_items: Array = []   # array of {id, count}
@export var dialog_lines: Array[String] = ["Hello, traveler."]
# Optional rich dialog tree.
# Schema: { "<node_id>": {
#     "text": "...",
#     "choices": [ {
#       "id": "choice_id",       # fired as Game.dialog_choice
#       "text": "shown to player",
#       "next": "<node_id>"|null,    # null/missing → close on click
#       "requires": {"flag":"value", ...}  # optional gating against quest flags
#       "actions": [                  # optional — interpreted by main.gd
#         "give_player:item_id",      # NPC -> player
#         "take_player:item_id",      # player -> NPC
#         "drop_inventory",           # NPC drops everything as pickups
#         "set_flag:key=value",       # set on every active quest
#         "die",                      # NPC dies (no loot drop animation, just queue_free with drop)
#         "remember:key=value"        # set on this NPC's own .memory dict
#       ]
#     } ]
# } }
@export var dialog_tree: Dictionary = {}
@export var dialog_start: String = "start"
# Prioritized list of start-node candidates. First entry whose `requires`
# matches (via QuestManager.state_match) is picked when the player opens a
# conversation. Falls back to `dialog_start` when none match.
# Each entry: {"node": "node_id", "requires": { ... }}.
@export var start_nodes: Array = []

# Per-NPC scratchpad the dialog system can write to with `remember:k=v`.
var memory: Dictionary = {}

# Resolves which start node to open when the player begins a conversation.
# Walks `start_nodes` top-to-bottom; returns the first whose requires-dict
# passes QuestManager.state_match. Falls back to `dialog_start`.
func resolve_start_node(player: Node, npcs_index: Dictionary) -> String:
	for entry in start_nodes:
		var node_id: String = String(entry.get("node", ""))
		var req: Dictionary = entry.get("requires", {})
		if node_id != "" and dialog_tree.has(node_id) \
			and QuestManager.state_match(req, player, npcs_index):
			return node_id
	return dialog_start

# Returns the choice list for a node with all `requires` predicates filtered
# out. Same predicate language as start_nodes.
func visible_choices(node_id: String, player: Node, npcs_index: Dictionary) -> Array:
	var node: Dictionary = dialog_tree.get(node_id, {})
	var raw: Array = node.get("choices", [])
	var out: Array = []
	for c in raw:
		var req: Dictionary = c.get("requires", {})
		if QuestManager.state_match(req, player, npcs_index):
			out.append(c)
	return out

var inventory: Inventory = Inventory.new()
var health: int

var _sprite: AnimatedSprite2D
var _hurtbox: Hurtbox

static func from_dict(d: Dictionary) -> NPC:
	var n := NPC.new()
	n.npc_name = String(d.get("npc_name", "Stranger"))
	n.character_sheet = String(d.get("character_sheet", "Villager"))
	n.role = String(d.get("role", ""))
	n.max_health = int(d.get("max_health", 3))
	n.initial_items = d.get("initial_items", [])
	n.dialog_tree = d.get("dialog_tree", {})
	n.start_nodes = d.get("start_nodes", [])
	n.dialog_start = String(d.get("dialog_start", "start"))
	if d.has("dialog_lines"):
		n.dialog_lines.assign(d.get("dialog_lines", []))
	return n

func _ready() -> void:
	add_to_group("npc")
	add_to_group("interactable")
	health = max_health
	collision_layer = 1 << 2   # NPC
	collision_mask = 1 << 0    # World
	for entry in initial_items:
		inventory.add(entry.id, entry.get("count", 1))
	_build_visual()
	_build_collision()
	_build_hurtbox()

func _build_visual() -> void:
	_sprite = AnimatedSprite2D.new()
	var sf := SpriteFrames.new()
	var walk_path := "res://assets/characters/%s/Walk.png" % character_sheet
	if ResourceLoader.exists(walk_path):
		AnimUtil.build_4dir(load(walk_path), "idle", 16, 16, 1.0, 1, sf)
	_sprite.sprite_frames = sf
	if sf.has_animation("idle_down"):
		_sprite.play("idle_down")
	_sprite.position = Vector2(0, -8)
	add_child(_sprite)

func _build_collision() -> void:
	var s := CollisionShape2D.new()
	var r := RectangleShape2D.new()
	r.size = Vector2(10, 6)
	s.shape = r
	s.position = Vector2(0, -2)
	add_child(s)

func _build_hurtbox() -> void:
	_hurtbox = Hurtbox.new()
	_hurtbox.owner_team = "npc"
	var s := CollisionShape2D.new()
	var c := CircleShape2D.new()
	c.radius = 7.0
	s.shape = c
	_hurtbox.add_child(s)
	_hurtbox.position = Vector2(0, -8)
	_hurtbox.hit.connect(_on_hurt)
	add_child(_hurtbox)

func _on_hurt(damage: int, _source: Node) -> void:
	health = max(0, health - damage)
	_flash()
	if health <= 0:
		_die()

func _flash() -> void:
	_sprite.modulate = Color(1, 0.4, 0.4)
	var t := get_tree().create_timer(0.12)
	t.timeout.connect(func(): _sprite.modulate = Color(1, 1, 1))

func _die() -> void:
	# scatter inventory
	for i in Inventory.SLOT_COUNT:
		var s = inventory.slots[i]
		if s != null:
			var off := Vector2(randf_range(-12, 12), randf_range(-12, 12))
			ItemPickup.spawn(get_parent(), s.id, s.count, global_position + off)
	Game.npc_killed.emit(npc_name)
	Game.log_event("npc_killed", npc_name)
	queue_free()
