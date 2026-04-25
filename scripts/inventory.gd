class_name Inventory
extends RefCounted

signal changed

const SLOT_COUNT := 9

var slots: Array = []
var selected: int = 0

func _init() -> void:
	slots.resize(SLOT_COUNT)
	for i in SLOT_COUNT:
		slots[i] = null

func add(id: String, count: int = 1) -> int:
	if count <= 0 or not ItemDB.has(id):
		return count
	var stackable: bool = ItemDB.get_item(id).get("stackable", false)
	if stackable:
		for i in SLOT_COUNT:
			var s = slots[i]
			if s != null and s.id == id:
				s.count += count
				changed.emit()
				return 0
	for i in SLOT_COUNT:
		if slots[i] == null:
			slots[i] = {"id": id, "count": count}
			changed.emit()
			return 0
	return count

func remove_one(slot_idx: int) -> Dictionary:
	if slot_idx < 0 or slot_idx >= SLOT_COUNT or slots[slot_idx] == null:
		return {}
	var s = slots[slot_idx]
	var taken := {"id": s.id, "count": 1}
	s.count -= 1
	if s.count <= 0:
		slots[slot_idx] = null
	changed.emit()
	return taken

func remove_all(slot_idx: int) -> Dictionary:
	if slot_idx < 0 or slot_idx >= SLOT_COUNT or slots[slot_idx] == null:
		return {}
	var taken: Dictionary = slots[slot_idx]
	slots[slot_idx] = null
	changed.emit()
	return taken

func first_nonempty_slot() -> int:
	for i in SLOT_COUNT:
		if slots[i] != null:
			return i
	return -1

func is_empty() -> bool:
	return first_nonempty_slot() == -1

func get_selected() -> Dictionary:
	if selected >= 0 and selected < SLOT_COUNT and slots[selected] != null:
		return slots[selected]
	return {}

func cycle_selected(delta: int) -> void:
	selected = (selected + delta) % SLOT_COUNT
	if selected < 0:
		selected += SLOT_COUNT
	changed.emit()

func set_selected(idx: int) -> void:
	if idx >= 0 and idx < SLOT_COUNT:
		selected = idx
		changed.emit()
