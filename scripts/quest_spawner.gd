class_name QuestSpawner
extends RefCounted

# Wipes existing quest content from the world and rebuilds from a validated
# bundle. Pure data → scene transformation. Caller supplies references to:
#   level_root  — Node2D where NPCs and item pickups live
#   player      — Player instance (used only for `near_player` position hints)
#   storyteller — Node to preserve across rebuilds
#
# Position-hint resolution uses the same 40×30 grid as main.gd's _build_floor.

const TILE := 16
const W := 40
const H := 30

static func spawn(bundle: Dictionary, level_root: Node, player: Node, storyteller = null) -> void:
	# 1. Wipe existing NPCs and pickups, except whichever nodes the
	# caller asked us to preserve. `storyteller` may be either a single
	# Node (legacy) or an Array of Nodes (multiple quest-givers to
	# survive the rebuild).
	var keep_set: Dictionary = {}
	if storyteller is Node:
		keep_set[storyteller] = true
	elif storyteller is Array:
		for n in storyteller:
			if n is Node: keep_set[n] = true
	_wipe(level_root, keep_set)
	# 2. Reset quest manager state so a previous quest doesn't leak.
	QuestManager.active_quests.clear()
	QuestManager.completed_quests.clear()
	QuestManager.global_flags.clear()
	# 3. Spawn NPCs. Distribute hints so two NPCs never collide at the same spot.
	var used_positions: Array[Vector2] = []
	for npc_dict in bundle.get("npcs", []):
		var n := NPC.from_dict(npc_dict)
		var pos := _resolve_position(String(npc_dict.get("position_hint","center")), player)
		pos = _avoid_collision(pos, used_positions)
		used_positions.append(pos)
		n.position = pos
		level_root.add_child(n)
		# Floating name label above the sprite so the player can spot NPCs
		# even when they're at the level's edge.
		level_root.add_child(_label_at(pos + Vector2(0, -22), n.npc_name))
	# 4. Spawn world items.
	for item_dict in bundle.get("items", []):
		var id: String = String(item_dict.get("id",""))
		if not ItemDB.has(id):
			continue
		var pos := _resolve_position(String(item_dict.get("position_hint","center")), player)
		pos = _avoid_collision(pos, used_positions)
		ItemPickup.spawn(level_root, id, int(item_dict.get("count", 1)), pos)
	# 5. Add the quest itself.
	QuestManager.add_quest_from_dict(bundle.get("quest", {}))

static func _wipe(level_root: Node, keep_set: Dictionary) -> void:
	var to_free: Array = []
	for child in level_root.get_children():
		if keep_set.has(child):
			continue
		if child is NPC or child is ItemPickup:
			to_free.append(child)
	for c in to_free:
		c.queue_free()

static func _resolve_position(hint: String, player: Node) -> Vector2:
	# Pull positions in toward the centre so NPCs stay in the playable
	# field instead of being lost in the corners (especially the SE combat
	# arena pen). Positions are within ~6 tiles of where the player can
	# walk; the camera (2× zoom) reveals each as the player approaches.
	var cx := W * TILE / 2.0
	var cy := H * TILE / 2.0
	var dx := 8.0 * TILE   # 128 px from centre on the X axis
	var dy := 6.0 * TILE   # 96 px from centre on the Y axis
	match hint:
		"nw": return Vector2(cx - dx, cy - dy)
		"ne": return Vector2(cx + dx, cy - dy)
		"sw": return Vector2(cx - dx, cy + dy)
		"se": return Vector2(cx + dx - 4 * TILE, cy + dy - 2 * TILE)   # nudge clear of arena pen
		"n":  return Vector2(cx,       cy - dy)
		"s":  return Vector2(cx,       cy + dy - 2 * TILE)
		"e":  return Vector2(cx + dx,  cy)
		"w":  return Vector2(cx - dx,  cy)
		"center": return Vector2(cx, cy)
		"near_player":
			if player != null and "global_position" in player:
				return player.global_position + Vector2(28, 0)
			return Vector2(cx, cy)
	return Vector2(cx, cy)

static func _avoid_collision(pos: Vector2, used: Array) -> Vector2:
	# Nudge the spawn point if another NPC/item already claimed the spot.
	var p := pos
	var attempts := 0
	while attempts < 8:
		var clash := false
		for u in used:
			if (u as Vector2).distance_to(p) < 24.0:
				clash = true
				break
		if not clash: return p
		p += Vector2(20, 14)
		attempts += 1
	return p

static func _label_at(pos: Vector2, text: String) -> Control:
	var l := Label.new()
	l.text = text
	l.position = pos - Vector2(text.length() * 3.0, 0)
	l.add_theme_color_override("font_color", Color(1, 1, 1))
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0))
	l.add_theme_constant_override("outline_size", 2)
	l.add_theme_font_size_override("font_size", 8)
	return l
