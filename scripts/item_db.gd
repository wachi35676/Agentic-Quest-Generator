extends Node

const ITEMS_DIR := "res://assets/items/"

var catalog: Dictionary = {}

func _ready() -> void:
	_register("stone",        "Stone",         true)
	_register("branch",       "Branch",        true)
	_register("feather",      "Feather",       true)
	_register("grass",        "Grass",         true)
	_register("gem_red",      "Red Gem",       true)
	_register("gem_green",    "Green Gem",     true)
	_register("key_gold",     "Gold Key",      false)
	_register("key_silver",   "Silver Key",    false)
	_register("coin_gold",    "Gold Coin",     true)
	_register("coin_silver",  "Silver Coin",   true)
	_register("apple",        "Apple",         true)
	_register("meat",         "Meat",          true)
	_register("honey",        "Honey",         true)
	_register("fish",         "Fish",          true)
	_register("potion_red",   "Red Potion",    true)
	_register("potion_blue",  "Blue Potion",   true)
	_register("potion_white", "White Potion",  true)
	_register("medipack",     "Medipack",      true)
	_register("heart",        "Heart",         true)
	_register("book",         "Book",          false)
	_register("letter",       "Letter",        false)
	_register("pickaxe",      "Pickaxe",       false)
	_register("axe",          "Axe",           false)
	_register("sword",        "Sword",         false)

const WEAPONS := {
	"sword":   {"damage": 2, "reach": 14.0, "radius": 9.0, "lock": 0.25},
	"axe":     {"damage": 3, "reach": 12.0, "radius": 9.0, "lock": 0.40},
	"pickaxe": {"damage": 1, "reach": 10.0, "radius": 6.0, "lock": 0.30},
}

static func is_weapon(id: String) -> bool:
	return WEAPONS.has(id)

static func weapon_stats(id: String) -> Dictionary:
	return WEAPONS.get(id, {})

func _register(id: String, display: String, stackable: bool) -> void:
	var path := ITEMS_DIR + id + ".png"
	var tex: Texture2D = null
	if ResourceLoader.exists(path):
		tex = load(path)
	else:
		push_warning("ItemDB: missing texture for '%s' at %s" % [id, path])
	catalog[id] = {
		"id": id,
		"name": display,
		"texture": tex,
		"stackable": stackable,
	}

func has(id: String) -> bool:
	return catalog.has(id)

func get_item(id: String) -> Dictionary:
	return catalog.get(id, {})

func get_texture(id: String) -> Texture2D:
	var d: Dictionary = catalog.get(id, {})
	return d.get("texture", null)

func all_ids() -> Array:
	return catalog.keys()
