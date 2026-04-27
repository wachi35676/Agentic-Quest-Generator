class_name QuestLog
extends CanvasLayer

var _root: Control
var _panel: PanelContainer
var _list: VBoxContainer
var _toast: Label
var _toast_timer: Timer
var _open: bool = false
var _banner: PanelContainer
var _banner_timer: Timer

func _ready() -> void:
	layer = 11
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	_build_panel()
	_build_toast()
	_build_banner()
	QuestManager.quest_added.connect(_on_quest_added)
	QuestManager.quest_progress.connect(_on_quest_progress)
	QuestManager.quest_completed.connect(_on_quest_completed)
	QuestManager.quest_failed.connect(_on_quest_failed)

# --- panel ---
func _build_panel() -> void:
	_panel = PanelContainer.new()
	_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_panel.offset_left = -250
	_panel.offset_top = 50
	_panel.offset_right = -10
	_panel.custom_minimum_size = Vector2(240, 180)
	_panel.visible = false
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.05, 0.1, 0.92)
	sb.border_color = Color(1, 0.85, 0.2)
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(3)
	sb.content_margin_left = 8
	sb.content_margin_right = 8
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	_panel.add_theme_stylebox_override("panel", sb)
	_root.add_child(_panel)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 6)
	_panel.add_child(_list)

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_quest_log"):
		_open = not _open
		_panel.visible = _open
		if _open:
			_refresh()

func _refresh() -> void:
	for c in _list.get_children():
		c.queue_free()
	var title := Label.new()
	title.text = "QUESTS  (Tab)"
	title.add_theme_color_override("font_color", Color(1, 0.85, 0.2))
	_list.add_child(title)
	if QuestManager.active_quests.is_empty() and QuestManager.completed_quests.is_empty():
		var empty := Label.new()
		empty.text = "(no quests yet)"
		empty.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
		_list.add_child(empty)
		return
	for q in QuestManager.active_quests:
		_list.add_child(_quest_block(q, false))
	for q in QuestManager.completed_quests:
		_list.add_child(_quest_block(q, true))

func _quest_block(q: Quest, _done: bool) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	var t := Label.new()
	var status_str := "[active]"
	var status_color := Color(1, 1, 1)
	if q.status == Quest.Status.COMPLETED:
		status_str = "[done: %s]" % q.completed_branch_id
		status_color = Color(0.5, 1, 0.5)
	elif q.status == Quest.Status.FAILED:
		status_str = "[failed]"
		status_color = Color(1, 0.4, 0.4)
	t.text = "%s %s  %s" % [("•" if q.status == Quest.Status.ACTIVE else "■"), q.title, status_str]
	t.add_theme_color_override("font_color", status_color)
	box.add_child(t)
	if q.description != "":
		var d := Label.new()
		d.text = "  " + q.description
		d.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
		d.add_theme_font_size_override("font_size", 11)
		d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		d.custom_minimum_size = Vector2(220, 0)
		box.add_child(d)
	# primary path objectives (if any)
	for o in q.objectives:
		box.add_child(_objective_label(o, "    "))
	# branches: list with their own progress
	for b in q.branches:
		var hdr := Label.new()
		var avail := q.flags_match(b.requires_flags)
		var hdr_color := Color(1, 0.85, 0.2) if avail else Color(0.5, 0.5, 0.5)
		hdr.text = "    └ branch: %s%s" % [b.id, "" if avail else " (locked)"]
		hdr.add_theme_color_override("font_color", hdr_color)
		hdr.add_theme_font_size_override("font_size", 11)
		box.add_child(hdr)
		# Branch description (the LLM's narrative blurb) right under the header.
		var desc_str: String = String(b.description) if "description" in b else ""
		if desc_str != "":
			var d := Label.new()
			d.text = "        " + desc_str
			d.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85) if avail else Color(0.45, 0.45, 0.45))
			d.add_theme_font_size_override("font_size", 10)
			d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			d.custom_minimum_size = Vector2(220, 0)
			box.add_child(d)
		for o in b.objectives:
			box.add_child(_objective_label(o, "        "))
	return box

func _objective_label(o: Objective, indent: String) -> Label:
	var ol := Label.new()
	var prefix := indent + ("[x] " if o.is_done() else "[ ] ")
	ol.text = prefix + o.summary()
	ol.add_theme_color_override("font_color", Color(0.6, 1, 0.6) if o.is_done() else Color(1, 1, 1))
	ol.add_theme_font_size_override("font_size", 11)
	return ol

# --- toast (corner notification) ---
func _build_toast() -> void:
	_toast = Label.new()
	_toast.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_toast.offset_left = -250
	_toast.offset_top = 8
	_toast.offset_right = -10
	_toast.text = ""
	_toast.add_theme_color_override("font_color", Color(1, 0.85, 0.2))
	_toast.add_theme_color_override("font_outline_color", Color(0, 0, 0))
	_toast.add_theme_constant_override("outline_size", 2)
	_toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_root.add_child(_toast)
	_toast_timer = Timer.new()
	_toast_timer.one_shot = true
	_toast_timer.timeout.connect(func(): _toast.text = "")
	add_child(_toast_timer)

func _flash(text: String, color: Color = Color(1, 0.85, 0.2)) -> void:
	_toast.add_theme_color_override("font_color", color)
	_toast.text = text
	_toast_timer.start(2.2)

# --- callbacks ---
func _on_quest_added(q: Quest) -> void:
	_flash("New quest: " + q.title)
	if _open: _refresh()

func _on_quest_progress(q: Quest, _o: Objective) -> void:
	if _open: _refresh()

func _on_quest_completed(q: Quest) -> void:
	_flash("Quest complete: %s [%s]" % [q.title, q.completed_branch_id], Color(0.5, 1, 0.5))
	_show_banner("QUEST COMPLETE", q, Color(0.4, 1, 0.4))
	if _open: _refresh()

func _on_quest_failed(q: Quest) -> void:
	_flash("Quest FAILED: " + q.title, Color(1, 0.4, 0.4))
	_show_banner("QUEST FAILED", q, Color(1, 0.4, 0.4))
	if _open: _refresh()

# --- center-screen completion banner ---
func _build_banner() -> void:
	_banner = PanelContainer.new()
	_banner.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	_banner.offset_left = -180
	_banner.offset_right = 180
	_banner.offset_top = -70
	_banner.offset_bottom = 70
	_banner.visible = false
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.05, 0.08, 0.95)
	sb.set_border_width_all(3)
	sb.border_color = Color(1, 0.85, 0.2)
	sb.set_corner_radius_all(4)
	sb.content_margin_left = 14
	sb.content_margin_right = 14
	sb.content_margin_top = 10
	sb.content_margin_bottom = 10
	_banner.add_theme_stylebox_override("panel", sb)
	_root.add_child(_banner)
	_banner_timer = Timer.new()
	_banner_timer.one_shot = true
	_banner_timer.timeout.connect(func(): _banner.visible = false)
	add_child(_banner_timer)

func _show_banner(headline: String, q: Quest, color: Color) -> void:
	for c in _banner.get_children():
		c.queue_free()
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 4)
	_banner.add_child(v)
	var head := Label.new()
	head.text = headline
	head.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	head.add_theme_color_override("font_color", color)
	head.add_theme_color_override("font_outline_color", Color(0, 0, 0))
	head.add_theme_constant_override("outline_size", 3)
	head.add_theme_font_size_override("font_size", 22)
	v.add_child(head)
	var t := Label.new()
	t.text = q.title
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	t.add_theme_color_override("font_color", Color(1, 1, 1))
	t.add_theme_font_size_override("font_size", 16)
	v.add_child(t)
	if q.status == Quest.Status.COMPLETED:
		var br := Label.new()
		br.text = "Path: " + q.completed_branch_id
		br.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		br.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
		br.add_theme_font_size_override("font_size", 12)
		v.add_child(br)
		var rewards: Array = q.rewards
		for b in q.branches:
			if b.id == q.completed_branch_id:
				rewards = b.rewards
				break
		if not rewards.is_empty():
			var r := Label.new()
			var parts: Array[String] = []
			for rw in rewards:
				var nm: String = String(ItemDB.get_item(rw.get("item_id","")).get("name", rw.get("item_id","")))
				parts.append("%dx %s" % [int(rw.get("count", 1)), nm])
			r.text = "Reward: " + ", ".join(parts)
			r.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			r.add_theme_color_override("font_color", Color(1, 0.85, 0.4))
			r.add_theme_font_size_override("font_size", 12)
			v.add_child(r)
	_banner.visible = true
	_banner_timer.start(4.0)
