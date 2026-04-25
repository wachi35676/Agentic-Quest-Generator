class_name SlashFX
extends Node2D

# slash_curved.png is 128x32 = 8 cols x 2 rows of 16x16.
# We use the top row (8-frame swing) and rotate per-direction.

const SHEET_PATH := "res://assets/fx/slash_curved.png"
const FRAME_W := 16
const FRAME_H := 16
const FRAMES := 8
const FPS := 32.0

static func spawn(parent: Node, pos: Vector2, face_dir: Vector2i) -> SlashFX:
	var fx := SlashFX.new()
	fx.position = pos
	fx._face = face_dir
	parent.add_child(fx)
	return fx

var _face: Vector2i = Vector2i(1, 0)

func _ready() -> void:
	var spr := AnimatedSprite2D.new()
	var sf := SpriteFrames.new()
	sf.add_animation("swing")
	sf.set_animation_speed("swing", FPS)
	sf.set_animation_loop("swing", false)
	if ResourceLoader.exists(SHEET_PATH):
		var tex: Texture2D = load(SHEET_PATH)
		for i in FRAMES:
			var atlas := AtlasTexture.new()
			atlas.atlas = tex
			atlas.region = Rect2(i * FRAME_W, 0, FRAME_W, FRAME_H)
			sf.add_frame("swing", atlas)
	spr.sprite_frames = sf
	# The sheet's slash is drawn pointing right by default.
	# Rotate so it points in face_dir.
	var ang := atan2(float(_face.y), float(_face.x))
	spr.rotation = ang
	add_child(spr)
	spr.play("swing")
	spr.animation_finished.connect(queue_free)
