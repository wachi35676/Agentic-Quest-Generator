class_name Player
extends CharacterBody2D

const SPEED := 70.0
const PICKUP_RADIUS := 14.0
const INTERACT_RADIUS := 18.0
# unarmed defaults (used only for the swing animation lock; no damage/VFX)
const UNARMED_LOCK := 0.20

@export var character_name: String = "Knight"
@export var max_health: int = 5

var inventory: Inventory = Inventory.new()
var face_dir: Vector2i = Vector2i(0, 1)
var health: int = 5
var attacking: bool = false
var attack_timer: float = 0.0
var iframes: float = 0.0

var _spawn_pos: Vector2
var _sprite: AnimatedSprite2D
var _hurtbox: Hurtbox
var _pickup_area: Area2D
var _interact_area: Area2D
var _weapon_sprite: Sprite2D

signal health_changed(current: int, max_v: int)
signal request_interact(target: Node)

func _ready() -> void:
	add_to_group("player")
	health = max_health
	_spawn_pos = position
	collision_layer = 1 << 1   # Player
	collision_mask = 1 << 0    # World walls
	_build_visual()
	_build_collision()
	_build_hurtbox()
	_build_pickup_area()
	_build_interact_area()
	_build_weapon_sprite()
	inventory.changed.connect(_update_weapon_sprite)

func _build_visual() -> void:
	_sprite = AnimatedSprite2D.new()
	var sf := SpriteFrames.new()
	var walk_path := "res://assets/characters/%s/Walk.png" % character_name
	var attack_path := "res://assets/characters/%s/Attack.png" % character_name
	var idle_path := "res://assets/characters/%s/Idle.png" % character_name
	if ResourceLoader.exists(walk_path):
		AnimUtil.build_4dir(load(walk_path), "walk", 16, 16, 8.0, -1, sf)
	if ResourceLoader.exists(idle_path):
		AnimUtil.build_4dir(load(idle_path), "idle", 16, 16, 2.0, -1, sf)
	elif ResourceLoader.exists(walk_path):
		AnimUtil.build_4dir(load(walk_path), "idle", 16, 16, 1.0, 1, sf)
	if ResourceLoader.exists(attack_path):
		AnimUtil.build_4dir(load(attack_path), "attack", 16, 16, 8.0, -1, sf)
		for d in AnimUtil.DIRS:
			sf.set_animation_loop("attack_%s" % d, false)
	_sprite.sprite_frames = sf
	_sprite.position = Vector2(0, -8)
	add_child(_sprite)
	_play_idle()

func _build_collision() -> void:
	var s := CollisionShape2D.new()
	var r := RectangleShape2D.new()
	r.size = Vector2(10, 6)
	s.shape = r
	s.position = Vector2(0, -2)
	add_child(s)

func _build_hurtbox() -> void:
	_hurtbox = Hurtbox.new()
	_hurtbox.owner_team = "player"
	var s := CollisionShape2D.new()
	var c := CircleShape2D.new()
	c.radius = 6.0
	s.shape = c
	_hurtbox.add_child(s)
	_hurtbox.position = Vector2(0, -6)
	_hurtbox.hit.connect(_on_hurt)
	add_child(_hurtbox)

func _build_pickup_area() -> void:
	_pickup_area = Area2D.new()
	_pickup_area.collision_layer = 0
	_pickup_area.collision_mask = 1 << 4  # Pickup
	_pickup_area.monitoring = true
	var s := CollisionShape2D.new()
	var c := CircleShape2D.new()
	c.radius = PICKUP_RADIUS
	s.shape = c
	_pickup_area.add_child(s)
	add_child(_pickup_area)

func _build_weapon_sprite() -> void:
	# In-hand weapon overlay disabled: the Knight character has no matching
	# weapon sheet in the pack, so a static SpriteInHand looks wonky in 4
	# directions. Visual signal that you're armed = the slash VFX on attack.
	_weapon_sprite = Sprite2D.new()
	_weapon_sprite.visible = false
	add_child(_weapon_sprite)

# Per-direction (face_dir) → {pos, rotation_deg, flip_h, behind}
const _WEAPON_POSE := {
	"right": {"pos": Vector2(5, -6),  "rot": 0.0,    "flip": false, "behind": false},
	"left":  {"pos": Vector2(-5, -6), "rot": 0.0,    "flip": true,  "behind": false},
	"down":  {"pos": Vector2(4, -4),  "rot": 0.0,    "flip": false, "behind": false},
	"up":    {"pos": Vector2(-4, -4), "rot": 0.0,    "flip": true,  "behind": true},
}

const _ATTACK_POSE_DELTA := {
	"right": {"pos": Vector2(6, -7),  "rot": -45.0},
	"left":  {"pos": Vector2(-6, -7), "rot": 45.0},
	"down":  {"pos": Vector2(6, -3),  "rot": -90.0},
	"up":    {"pos": Vector2(-6, -10), "rot": 90.0},
}

func _update_weapon_sprite() -> void:
	# no-op while the in-hand overlay is disabled
	pass

func _apply_weapon_pose(during_attack: bool) -> void:
	if _weapon_sprite == null or not _weapon_sprite.visible:
		return
	var dir := AnimUtil.dir_name_from_vec(face_dir)
	var pose: Dictionary = _WEAPON_POSE.get(dir, _WEAPON_POSE["right"])
	var pos: Vector2 = pose.pos
	var rot: float = pose.rot
	if during_attack:
		var d: Dictionary = _ATTACK_POSE_DELTA.get(dir, _ATTACK_POSE_DELTA["right"])
		pos = d.pos
		rot = d.rot
	_weapon_sprite.position = pos
	_weapon_sprite.rotation_degrees = rot
	_weapon_sprite.flip_h = pose.flip
	_weapon_sprite.z_index = -1 if pose.behind else 0

func _build_interact_area() -> void:
	_interact_area = Area2D.new()
	_interact_area.collision_layer = 0
	_interact_area.collision_mask = (1 << 2) | (1 << 3)   # NPC + Enemy bodies (we use body-detection style here we only need NPCs in group "interactable")
	_interact_area.monitoring = true
	var s := CollisionShape2D.new()
	var c := CircleShape2D.new()
	c.radius = INTERACT_RADIUS
	s.shape = c
	_interact_area.add_child(s)
	add_child(_interact_area)

func _physics_process(delta: float) -> void:
	if iframes > 0.0:
		iframes -= delta
		_sprite.modulate.a = 0.4 if int(iframes * 20.0) % 2 == 0 else 1.0
	else:
		_sprite.modulate.a = 1.0

	if attacking:
		attack_timer -= delta
		velocity = Vector2.ZERO
		_apply_weapon_pose(true)
		move_and_slide()
		if attack_timer <= 0.0:
			attacking = false
			_apply_weapon_pose(false)
			_play_idle()
		return

	var input := Vector2(
		Input.get_action_strength("move_right") - Input.get_action_strength("move_left"),
		Input.get_action_strength("move_down") - Input.get_action_strength("move_up")
	)
	if input.length() > 0.01:
		var primary := input
		if abs(primary.x) > abs(primary.y):
			face_dir = Vector2i(sign(primary.x), 0)
		else:
			face_dir = Vector2i(0, sign(primary.y))
		velocity = input.normalized() * SPEED
		_play("walk")
	else:
		velocity = Vector2.ZERO
		_play("idle")
	_apply_weapon_pose(false)
	move_and_slide()

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("attack"):
		_start_attack()
	elif event.is_action_pressed("interact"):
		_try_interact()
	elif event.is_action_pressed("drop"):
		_drop_selected()
	elif event.is_action_pressed("slot_next"):
		inventory.cycle_selected(1)
	elif event.is_action_pressed("slot_prev"):
		inventory.cycle_selected(-1)
	elif event is InputEventKey and event.pressed and not event.echo:
		var k: int = event.keycode
		if k >= KEY_1 and k <= KEY_9:
			inventory.set_selected(k - KEY_1)

func _start_attack() -> void:
	if attacking: return
	attacking = true
	var weapon := _equipped_weapon()
	if weapon.is_empty():
		attack_timer = UNARMED_LOCK
		_play("attack")
		return
	var stats: Dictionary = ItemDB.weapon_stats(weapon.id)
	attack_timer = stats.get("lock", 0.25)
	_play("attack")
	var reach: float = stats.get("reach", 12.0)
	var radius: float = stats.get("radius", 7.0)
	var dmg: int = stats.get("damage", 1)
	var offset := Vector2(face_dir.x, face_dir.y) * reach
	var fx_pos := global_position + offset + Vector2(0, -6)
	Hitbox.spawn(get_parent(), fx_pos, radius, dmg, "player", self)
	SlashFX.spawn(get_parent(), fx_pos, face_dir)

func _equipped_weapon() -> Dictionary:
	var s := inventory.get_selected()
	if s.is_empty(): return {}
	if not ItemDB.is_weapon(s.id): return {}
	return s

func _try_interact() -> void:
	# Pickup has priority if any nearby
	var pickups := _pickup_area.get_overlapping_areas()
	var nearest_pickup: ItemPickup = null
	var nearest_d := INF
	for a in pickups:
		if a is ItemPickup:
			var d := a.global_position.distance_to(global_position)
			if d < nearest_d:
				nearest_d = d
				nearest_pickup = a
	if nearest_pickup != null:
		var leftover := inventory.add(nearest_pickup.item_id, nearest_pickup.count)
		if leftover < nearest_pickup.count:
			Game.item_picked_up.emit(nearest_pickup.item_id, nearest_pickup.count - leftover)
			Game.log_event("pickup", "%s x%d" % [nearest_pickup.item_id, nearest_pickup.count - leftover])
			nearest_pickup.queue_free()
		return
	# else: interact with NPC
	var bodies := _interact_area.get_overlapping_bodies()
	for b in bodies:
		if b.is_in_group("npc"):
			request_interact.emit(b)
			return

func _drop_selected() -> void:
	var s := inventory.get_selected()
	if s.is_empty():
		return
	var taken: Dictionary = inventory.remove_one(inventory.selected)
	if taken.is_empty():
		return
	var offset := Vector2(face_dir.x, face_dir.y) * 14.0
	ItemPickup.spawn(get_parent(), taken.id, taken.count, global_position + offset + Vector2(0, -4))
	Game.item_dropped.emit(taken.id, taken.count)
	Game.log_event("drop", taken.id)

func _on_hurt(damage: int, _source: Node) -> void:
	if iframes > 0.0:
		return
	health = max(0, health - damage)
	iframes = 0.5
	health_changed.emit(health, max_health)
	Game.player_damaged.emit(damage, health)
	if health <= 0:
		_respawn()

func _respawn() -> void:
	position = _spawn_pos
	health = max_health
	health_changed.emit(health, max_health)

func _play_idle() -> void:
	_play("idle")

func _play(state: String) -> void:
	if _sprite.sprite_frames == null: return
	var anim := "%s_%s" % [state, AnimUtil.dir_name_from_vec(face_dir)]
	if _sprite.sprite_frames.has_animation(anim) and _sprite.animation != anim:
		_sprite.play(anim)
