class_name WorldCatalog
extends RefCounted

# Single source of truth for what the LLM is allowed to reference. Read live
# from ItemDB + the assets/ folder so adding a character sheet or item
# doesn't require updating a separate list.

const POSITION_HINTS := ["ne","nw","se","sw","n","s","e","w","center","near_player"]
const OBJECTIVE_TYPES := ["collect","drop","give","take","talk","kill_enemy","kill_npc","dialog_choice","reach"]
const ACTION_PREFIXES := ["give_player","take_player","set_flag","remember"]
const ACTION_BARE := ["drop_inventory","die"]
const PREDICATE_PREFIXES := ["flag","quest","inv","memory"]

static func item_ids() -> Array:
	return ItemDB.all_ids()

static func weapon_ids() -> Array:
	return ItemDB.WEAPONS.keys()

static func character_sheets() -> Array:
	return _list_subfolders("res://assets/characters/")

static func monster_sheets() -> Array:
	return _list_subfolders("res://assets/monsters/")

static func _list_subfolders(path: String) -> Array:
	var out: Array = []
	var dir := DirAccess.open(path)
	if dir == null:
		return out
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if dir.current_is_dir() and not name.begins_with("."):
			out.append(name)
		name = dir.get_next()
	dir.list_dir_end()
	out.sort()
	return out
