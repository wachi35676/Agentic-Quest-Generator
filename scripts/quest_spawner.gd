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
		# Floating name label as a CHILD of the NPC (relative offset).
		# Adding to level_root as a sibling worked but left orphan labels
		# floating on the map after the NPC was freed during a chapter
		# change — _wipe only frees NPC/ItemPickup nodes, not Controls.
		var label := _label_at(Vector2(0, -22), n.npc_name)
		n.add_child(label)
	# 4. Spawn world items — only those relevant to the quest. Models often
	# dump every catalog id with position_hint:center, which floods the
	# screen. Filter to items referenced in any quest objective, plus
	# items inside spawned NPC inventories. Cap total to 5.
	var relevant: Dictionary = _collect_relevant_item_ids(bundle)
	var spawned: int = 0
	for item_dict in bundle.get("items", []):
		if spawned >= 5:
			break
		var id: String = String(item_dict.get("id",""))
		if not ItemDB.has(id):
			continue
		# If we have ANY relevant items, only spawn those. Otherwise
		# spawn all (fallback for quests that don't reference items).
		if not relevant.is_empty() and not relevant.has(id):
			continue
		var pos := _resolve_position(String(item_dict.get("position_hint","center")), player)
		pos = _avoid_collision(pos, used_positions)
		ItemPickup.spawn(level_root, id, int(item_dict.get("count", 1)), pos)
		spawned += 1
	# 5. Finally — register the quest itself with the manager. Without this,
	# QuestManager.active_quests stays empty and Tab shows "no quests yet".
	# When the bundle is delivered through the Wanderer-orchestrator flow,
	# bundle.quest.orchestrator_managed=true on the dict; the engine then
	# disables auto-completion so the Wanderer is the only one who can
	# close the quest.
	var quest_dict: Dictionary = bundle.get("quest", {})
	var q := QuestManager.add_quest_from_dict(quest_dict)
	if bool(quest_dict.get("orchestrator_managed", false)):
		q.meta["orchestrator_managed"] = true
	print("[spawner] registered quest '%s' (id=%s, branches=%d, orchestrator=%s)" % [
			q.title, q.id, q.branches.size(),
			str(q.meta.get("orchestrator_managed", false))])

static func _collect_relevant_item_ids(bundle: Dictionary) -> Dictionary:
	var ids: Dictionary = {}
	var quest: Dictionary = bundle.get("quest", {})
	for o in quest.get("objectives", []):
		var iid: String = String((o.get("params", {}) as Dictionary).get("item_id",""))
		if iid != "": ids[iid] = true
	for b in quest.get("branches", []):
		for o in b.get("objectives", []):
			var iid2: String = String((o.get("params", {}) as Dictionary).get("item_id",""))
			if iid2 != "": ids[iid2] = true
		for r in b.get("rewards", []):
			var rid: String = String((r as Dictionary).get("item_id",""))
			if rid != "": ids[rid] = true
	return ids
	# 5. Add the quest itself.
	QuestManager.add_quest_from_dict(bundle.get("quest", {}))

static func _wipe(level_root: Node, keep_set: Dictionary) -> void:
	var to_free: Array = []
	for child in level_root.get_children():
		if keep_set.has(child):
			continue
		if child is NPC or child is ItemPickup:
			to_free.append(child)
		# Sweep stranded floating labels. Labels are now parented to NPCs
		# but pre-fix builds may leave orphan Controls in level_root, and
		# defending against future regressions is cheap.
		elif child is Label:
			to_free.append(child)
	for c in to_free:
		c.queue_free()
	print("[spawner] wiped %d nodes (kept %d hand-placed)" % [to_free.size(), keep_set.size()])

static func _resolve_position(hint: String, player: Node) -> Vector2:
	# Spawn around the player — they're standing next to the quest-giver
	# at accept time, so this clusters the spawned NPCs near where the
	# story kicked off. The Wanderer's new location at (-288, -120) has
	# walkable grass on its east/south side; pre-existing edges that
	# were tree-bound are no longer at the spawn anchor.
	var origin: Vector2 = Vector2(64, 48)
	if player != null and "global_position" in player:
		origin = player.global_position
	# Compass offsets in pixels (~ 4-7 tiles from the player). Far enough
	# that NPCs feel "out there" but close enough they're discoverable
	# via short exploration in any direction.
	var d_near: float = 64.0     # 4 tiles
	var d_far: float  = 112.0    # 7 tiles
	match hint:
		"nw": return origin + Vector2(-d_far, -d_near)
		"ne": return origin + Vector2( d_far, -d_near)
		"sw": return origin + Vector2(-d_far,  d_near)
		"se": return origin + Vector2( d_far,  d_near)
		"n":  return origin + Vector2(0,      -d_far)
		"s":  return origin + Vector2(0,       d_far)
		"e":  return origin + Vector2( d_far,  0)
		"w":  return origin + Vector2(-d_far,  0)
		"center": return origin
		"near_player": return origin + Vector2(28, 0)
	return origin

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
