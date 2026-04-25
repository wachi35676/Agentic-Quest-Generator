class_name Enemy
extends CharacterBody2D

enum State { IDLE, CHASE, ATTACK, COOLDOWN }

@export var enemy_type: String = "Slime"   # folder under assets/monsters/
@export var max_health: int = 2
@export var move_speed: float = 38.0
@export var detection_radius: float = 80.0
@export var attack_radius: float = 16.0
@export var damage: int = 1
@export var loot_table: Array[String] = ["grass"]

var health: int
var state: int = State.IDLE
var _state_timer: float = 0.0
var _player: Node2D = null

var _sprite: AnimatedSprite2D
var _hurtbox: Hurtbox

func _ready() -> void:
	add_to_group("enemy")
	health = max_health
	collision_layer = 1 << 3   # Enemy
	collision_mask = 1 << 0    # World walls
	_build_visual()
	_build_collision()
	_build_hurtbox()

func _build_visual() -> void:
	_sprite = AnimatedSprite2D.new()
	var sf := SpriteFrames.new()
	var sheet := "res://assets/monsters/%s/SpriteSheet.png" % enemy_type
	if ResourceLoader.exists(sheet):
		AnimUtil.build_4dir(load(sheet), "walk", 16, 16, 6.0, -1, sf)
		AnimUtil.build_4dir(load(sheet), "idle", 16, 16, 1.0, 1, sf)
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
	_hurtbox.owner_team = "enemy"
	var s := CollisionShape2D.new()
	var c := CircleShape2D.new()
	c.radius = 6.0
	s.shape = c
	_hurtbox.add_child(s)
	_hurtbox.position = Vector2(0, -6)
	_hurtbox.hit.connect(_on_hurt)
	add_child(_hurtbox)

func _physics_process(delta: float) -> void:
	if _player == null:
		_player = get_tree().get_first_node_in_group("player")
	if _player == null:
		return
	var to_player: Vector2 = _player.global_position - global_position
	var dist: float = to_player.length()
	match state:
		State.IDLE:
			velocity = Vector2.ZERO
			if dist <= detection_radius:
				state = State.CHASE
		State.CHASE:
			if dist > detection_radius * 1.4:
				state = State.IDLE
			elif dist <= attack_radius:
				state = State.ATTACK
				_state_timer = 0.3
			else:
				velocity = to_player.normalized() * move_speed
				_face(to_player)
				_play("walk")
		State.ATTACK:
			velocity = Vector2.ZERO
			_state_timer -= delta
			_play("idle")
			if _state_timer <= 0.0:
				_face(to_player)
				var off: Vector2 = to_player.normalized() * 10.0
				Hitbox.spawn(get_parent(), global_position + off + Vector2(0, -6), 8.0, damage, "enemy", self)
				state = State.COOLDOWN
				_state_timer = 0.7
		State.COOLDOWN:
			velocity = Vector2.ZERO
			_state_timer -= delta
			if _state_timer <= 0.0:
				state = State.CHASE
	move_and_slide()

func _face(v: Vector2) -> void:
	if abs(v.x) > abs(v.y):
		_facing = Vector2i(sign(v.x), 0)
	else:
		_facing = Vector2i(0, sign(v.y))

var _facing: Vector2i = Vector2i(0, 1)

func _play(state_name: String) -> void:
	if _sprite.sprite_frames == null: return
	var anim := "%s_%s" % [state_name, AnimUtil.dir_name_from_vec(_facing)]
	if _sprite.sprite_frames.has_animation(anim) and _sprite.animation != anim:
		_sprite.play(anim)

func _on_hurt(dmg: int, _source: Node) -> void:
	health = max(0, health - dmg)
	_sprite.modulate = Color(1, 0.4, 0.4)
	var t := get_tree().create_timer(0.1)
	t.timeout.connect(func(): _sprite.modulate = Color(1, 1, 1))
	if health <= 0:
		_die()

func _die() -> void:
	if not loot_table.is_empty():
		var pick: String = loot_table[randi() % loot_table.size()]
		ItemPickup.spawn(get_parent(), pick, 1, global_position + Vector2(0, -4))
	Game.enemy_killed.emit(enemy_type)
	Game.log_event("enemy_killed", enemy_type)
	queue_free()
