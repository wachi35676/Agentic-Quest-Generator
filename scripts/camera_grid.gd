class_name CameraGrid
extends Camera2D

# Port of NinjaAdventure/system/camera/camera_grid.gd. Instead of a smooth
# follow, the camera snaps to a fixed grid of "rooms" — when the player
# crosses a cell boundary, the camera tweens to the new cell over
# transition_time. Gives the same room-by-room feel as the reference game
# (and the original Zelda).
#
# Grid math is based on viewport ÷ zoom: at 480×320 with zoom 2 the visible
# world rectangle is 240×160, which is exactly one cell.

signal cell_changed
signal animation_finished

@export var grid_size: Vector2 = Vector2(320, 176)
@export var current_cell: Vector2 = Vector2.ZERO:
	set(v):
		if current_cell == v: return
		current_cell = v
		cell_changed.emit()
@export var animation_trans: Tween.TransitionType = Tween.TRANS_SINE
@export var animation_ease: Tween.EaseType = Tween.EASE_IN_OUT
@export var transition_time: float = 0.8

var target: Node2D = null:
	set(v):
		target = v
		set_process(target != null)

var _tween: Tween

func _ready() -> void:
	add_to_group("camera")
	if target != null:
		current_cell = world_to_grid(target.global_position)
		global_position = grid_to_world(current_cell)
	set_process(target != null)

func _process(_delta: float) -> void:
	if target == null:
		set_process(false)
		return
	var t_cell := world_to_grid(target.global_position)
	if t_cell != current_cell:
		go_to_cell(t_cell)

func go_to_cell(cell_target: Vector2) -> void:
	current_cell = cell_target
	if _tween != null:
		_tween.kill()
	_tween = create_tween()
	_tween.tween_property(self, "position", grid_to_world(current_cell), transition_time) \
		.set_trans(animation_trans).set_ease(animation_ease)
	await _tween.finished
	animation_finished.emit()

func teleport_to(world_pos: Vector2) -> void:
	if _tween != null: _tween.kill()
	current_cell = world_to_grid(world_pos)
	global_position = grid_to_world(current_cell)

func world_to_grid(pos: Vector2) -> Vector2:
	# Reference uses round(): cell boundaries fall at half-grid positions
	# (i.e. on the village's room-divider walls), so the camera flips just
	# as the player crosses a wall, not in the middle of a corridor.
	return ((pos - offset) / grid_size).round()

func grid_to_world(cell: Vector2) -> Vector2:
	# Reference convention: camera position == cell index × grid_size.
	# That's the centre of the cell because cells are anchored on
	# multiples of grid_size with round() boundaries.
	return cell * grid_size
