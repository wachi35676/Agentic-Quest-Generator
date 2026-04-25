class_name Hud
extends CanvasLayer

const HOTBAR_CELL := 28

var player: Player = null
var _root: Control
var _hearts: HBoxContainer
var _hotbar: HBoxContainer
var _msg: Label
var _msg_timer: Timer

func _ready() -> void:
	layer = 10
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	_build_hearts()
	_build_hotbar()
	_build_msg()

func bind_player(p: Player) -> void:
	player = p
	p.health_changed.connect(_on_health_changed)
	p.inventory.changed.connect(_on_inv_changed)
	_on_health_changed(p.health, p.max_health)
	_on_inv_changed()

# ---- hearts (top-left) ----
func _build_hearts() -> void:
	var bar := HBoxContainer.new()
	bar.position = Vector2(6, 4)
	bar.add_theme_constant_override("separation", 2)
	_root.add_child(bar)
	_hearts = bar

func _on_health_changed(current: int, max_v: int) -> void:
	for c in _hearts.get_children():
		c.queue_free()
	# Heart.png is 80x16 = 5 cells of 16x16: cell 0 = empty ... cell 4 = full.
	var bar_path := "res://assets/items/heart_bar.png"
	var bar_tex: Texture2D = load(bar_path) if ResourceLoader.exists(bar_path) else null
	for i in max_v:
		var t := TextureRect.new()
		if bar_tex != null:
			var atlas := AtlasTexture.new()
			atlas.atlas = bar_tex
			atlas.region = Rect2(4 * 16 if i < current else 0, 0, 16, 16)
			t.texture = atlas
		t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		t.custom_minimum_size = Vector2(36, 36)
		_hearts.add_child(t)

# ---- hotbar (bottom-center) ----
func _build_hotbar() -> void:
	# Wrap in a full-width CenterContainer pinned to the bottom so the inner
	# HBox sizes to its children (cells) and is centered horizontally.
	var bar_holder := CenterContainer.new()
	bar_holder.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	bar_holder.offset_top = -HOTBAR_CELL - 8
	bar_holder.offset_bottom = -6
	bar_holder.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(bar_holder)
	_hotbar = HBoxContainer.new()
	_hotbar.add_theme_constant_override("separation", 2)
	bar_holder.add_child(_hotbar)

func _on_inv_changed() -> void:
	if player == null: return
	for c in _hotbar.get_children():
		c.queue_free()
	for i in Inventory.SLOT_COUNT:
		_hotbar.add_child(_make_cell(i))

func _make_cell(i: int) -> Control:
	var slot = player.inventory.slots[i]
	var cell := PanelContainer.new()
	cell.custom_minimum_size = Vector2(HOTBAR_CELL, HOTBAR_CELL)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.05, 0.1, 0.75)
	sb.set_border_width_all(2)
	sb.border_color = Color(1, 0.85, 0.2) if i == player.inventory.selected else Color(0.4, 0.4, 0.5)
	sb.set_corner_radius_all(2)
	cell.add_theme_stylebox_override("panel", sb)
	# slot number label (top-left, drawn over the panel)
	var num := Label.new()
	num.text = str(i + 1)
	num.add_theme_color_override("font_color", Color(1, 1, 1, 0.85))
	num.add_theme_color_override("font_outline_color", Color(0, 0, 0))
	num.add_theme_constant_override("outline_size", 2)
	num.add_theme_font_size_override("font_size", 9)
	num.position = Vector2(2, -1)
	num.mouse_filter = Control.MOUSE_FILTER_IGNORE
	num.z_index = 1
	cell.add_child(num)
	if slot != null:
		var icon := TextureRect.new()
		icon.texture = ItemDB.get_texture(slot.id)
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.custom_minimum_size = Vector2(HOTBAR_CELL - 8, HOTBAR_CELL - 8)
		icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		cell.add_child(icon)
		if slot.count > 1:
			var cnt := Label.new()
			cnt.text = "x%d" % slot.count
			cnt.add_theme_color_override("font_color", Color(1, 1, 1))
			cnt.add_theme_color_override("font_outline_color", Color(0, 0, 0))
			cnt.add_theme_constant_override("outline_size", 2)
			cnt.add_theme_font_size_override("font_size", 10)
			cnt.position = Vector2(HOTBAR_CELL - 18, HOTBAR_CELL - 14)
			cnt.mouse_filter = Control.MOUSE_FILTER_IGNORE
			cnt.z_index = 1
			cell.add_child(cnt)
	return cell

# ---- toast ----
func _build_msg() -> void:
	_msg = Label.new()
	_msg.position = Vector2(40, 50)
	_msg.add_theme_color_override("font_color", Color(1, 1, 0.6))
	_msg.add_theme_color_override("font_outline_color", Color(0, 0, 0))
	_msg.add_theme_constant_override("outline_size", 2)
	_root.add_child(_msg)
	_msg_timer = Timer.new()
	_msg_timer.one_shot = true
	_msg_timer.timeout.connect(func(): _msg.text = "")
	add_child(_msg_timer)

func toast(text: String, duration: float = 1.6) -> void:
	_msg.text = text
	_msg_timer.start(duration)
