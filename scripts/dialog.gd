class_name DialogBox
extends CanvasLayer

# Dialog UI supporting:
#   - simple action prompts (Talk / Give / Take / Cancel)
#   - inventory pickers (give/take from a target inventory)
#   - branching dialog trees (each node has text + choices, choices have id +
#     next + actions + a `requires` predicate over flags)
#
# All branching state is owned by `main.gd` via the actions emitted on each
# choice — this UI is a pure renderer.

signal closed
signal action_chosen(action: String)
signal item_chosen(slot_idx: int)
signal choice_chosen(choice: Dictionary)   # the full choice dict

var _panel: PanelContainer
var _content: VBoxContainer
var _title: Label
var _body: Label
var _buttons: VBoxContainer

func _ready() -> void:
	layer = 20
	_panel = PanelContainer.new()
	_panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	_panel.offset_left = 20
	_panel.offset_right = -20
	_panel.offset_top = -260      # taller — fits long branching dialog
	_panel.offset_bottom = -10
	add_child(_panel)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.05, 0.1, 0.92)
	sb.border_color = Color(1, 1, 1)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(2)
	sb.content_margin_left = 8
	sb.content_margin_right = 8
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	_panel.add_theme_stylebox_override("panel", sb)
	_content = VBoxContainer.new()
	_content.add_theme_constant_override("separation", 4)
	_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_panel.add_child(_content)
	_title = Label.new()
	_title.add_theme_color_override("font_color", Color(1, 0.9, 0.4))
	_title.add_theme_font_size_override("font_size", 13)
	_content.add_child(_title)
	# Body in its own scroll container — long story dialog can be many lines.
	var body_scroll := ScrollContainer.new()
	body_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body_scroll.custom_minimum_size = Vector2(0, 90)
	_content.add_child(body_scroll)
	_body = Label.new()
	_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_body.add_theme_font_size_override("font_size", 11)
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body_scroll.add_child(_body)
	# Buttons go in their own scroll container.
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_content.add_child(scroll)
	_buttons = VBoxContainer.new()
	_buttons.add_theme_constant_override("separation", 2)
	_buttons.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_buttons)

func show_actions(title: String, body: String, actions: Array) -> void:
	_title.text = title
	_body.text = body
	_clear_buttons()
	for a in actions:
		_make_button(a, func(): action_chosen.emit(a))
	_make_button("Close", close_dialog)
	visible = true

func _make_button(label: String, on_press: Callable) -> Button:
	var btn := Button.new()
	btn.text = label
	btn.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	btn.clip_text = false
	btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	btn.add_theme_font_size_override("font_size", 11)
	btn.custom_minimum_size = Vector2(0, 24)
	btn.pressed.connect(on_press)
	_buttons.add_child(btn)
	return btn

func show_inventory_picker(title: String, body: String, inv: Inventory) -> void:
	_title.text = title
	_body.text = body
	_clear_buttons()
	var any := false
	for i in Inventory.SLOT_COUNT:
		var s = inv.slots[i]
		if s == null: continue
		any = true
		var d: Dictionary = ItemDB.get_item(s.id)
		var btn := _make_button("%s x%d" % [d.get("name", s.id), s.count], func(): item_chosen.emit(i))
		btn.icon = d.get("texture", null)
	if not any:
		var lbl := Label.new()
		lbl.text = "(empty)"
		_buttons.add_child(lbl)
	_make_button("Cancel", close_dialog)
	visible = true

# Show a tree dialog node. `node` is the dialog node dict; `choices` is
# pre-filtered (gating already applied by caller).
func show_node(title: String, node: Dictionary, choices: Array, extra_actions: Array = []) -> void:
	_title.text = title
	_body.text = node.get("text", "")
	_clear_buttons()
	for c in choices:
		var choice_dict: Dictionary = c
		_make_button(c.get("text", "(silent)"), func(): choice_chosen.emit(choice_dict))
	# Extra action buttons (Give/Take) so the player can hand items to a
	# dialog-tree NPC even when the writer didn't include item-transfer
	# choices. Click → action_chosen("Give"|"Take") → main routes to the
	# standard inventory picker.
	for label in extra_actions:
		var lbl: String = String(label)
		_make_button("[%s]" % lbl, func(): action_chosen.emit(lbl))
	# Always offer a way out so the player isn't locked in if the dialog
	# choices are gated away or only Give/Take remain. Close shuts the
	# dialog without firing any action.
	_make_button("[Bye]", close_dialog)
	visible = true

func _clear_buttons() -> void:
	for c in _buttons.get_children():
		c.queue_free()

func close_dialog() -> void:
	visible = false
	closed.emit()
