extends Node2D

const TILE := 16
const W := 40   # tiles
const H := 30

var player: Player
var hud: Hud
var dialog: DialogBox
var quest_log: QuestLog
var camera: CameraGrid
var level_root: Node2D

var _current_npc: Node = null
var _dialog_state: String = ""   # "menu" / "give" / "take" / "tree"
var _dialog_node_id: String = ""

var quest_agent: QuestGenAgent

# The premise chosen at kickoff time, kept around so dialog expansions
# share the same world setup as the original generation.
var _current_premise: String = ""

# Per-quest record of the originating quest-giver's NPC. Keyed by quest.id.
var _quest_giver_for: Dictionary = {}

func _ready() -> void:
	randomize()
	# Use the imported Ninja Adventure village as the world. The scene
	# instances res://system/map/map.tscn (the base) and overrides the
	# Tilemap with hand-placed tile_data.
	var village_path := "res://content/map/map_village.tscn"
	if ResourceLoader.exists(village_path):
		var scene: PackedScene = load(village_path)
		level_root = scene.instantiate() as Node2D
		level_root.name = "Level"
		add_child(level_root)
	else:
		# Fallback for tests / pre-import: procedural floor.
		level_root = Node2D.new()
		level_root.name = "Level"
		add_child(level_root)
		_build_floor_and_walls()
	_spawn_player()
	_setup_camera()
	_setup_hud()
	_setup_dialog()
	_setup_quest_log()
	_setup_quest_agent()
	call_deferred("_spawn_quest_givers")

# Hand-placed quest-giver NPCs at known-walkable village coords (extracted
# from the reference map_village's character spawns). Each NPC issues a
# single LLM-generated simple quest the first time the player talks to
# them, then walks them through active/complete dialog states.
func _spawn_quest_givers() -> void:
	if get_tree().has_meta("skip_autogen") and bool(get_tree().get_meta("skip_autogen")):
		return
	# World coords (= reference local-to-Tilemap + Tilemap offset (8,-5)).
	_spawn_quest_giver("Farmer", "Villager", "farmer", LlmPrompts.SIMPLE_KIND_FETCH,
			Vector2(0, 0),
			"A weathered farmer leaning on a hoe.")
	_spawn_quest_giver("Hunter", "Hunter", "hunter", LlmPrompts.SIMPLE_KIND_KILL,
			Vector2(-80, -128),
			"A sharp-eyed hunter testing a bowstring.")
	_spawn_quest_giver("Old Sage", "OldMan", "elder", LlmPrompts.SIMPLE_KIND_FETCH,
			Vector2(128, 32),
			"An old sage with ink-stained fingers.")
	# Two-stage Mystic — issues a stage-1 fetch, then a stage-2 quest
	# whose contents depend on a moral choice the player makes after
	# turning in stage 1. Two LLM calls per playthrough of this quest.
	_spawn_quest_giver("Mystic", "Princess", "mystic", "two_stage",
			Vector2(-32, 96),
			"A veiled mystic. Her eyes don't quite focus on you.")
	# Wanderer — issues a fully dynamic, multi-branch quest. The LLM
	# emits 5-7 branches gated on PLAYER ACTIONS (talk vs kill vs give
	# vs ignore). The engine's existing dialog/flag system evaluates
	# the graph; no branch logic is hand-coded here.
	_spawn_quest_giver("Wanderer", "Monk", "wanderer", "branching",
			Vector2(-288, -120),
			"A travel-stained wanderer with a story behind their eyes.")

func _spawn_quest_giver(npc_name: String, sheet: String, role: String,
		kind: String, pos: Vector2, idle_line: String) -> void:
	var n := NPC.new()
	n.npc_name = npc_name
	n.character_sheet = sheet
	n.role = role
	n.dialog_lines = [idle_line]
	n.position = pos
	# Mark this NPC as a quest-giver so _on_player_interact knows to route
	# to the LLM flow instead of the default Talk/Give/Take menu.
	n.set_meta("quest_giver_kind", kind)
	level_root.add_child(n)
	# Floating name label as a CHILD of the NPC so it's freed automatically
	# if the NPC ever is. Hand-placed quest-givers are invulnerable, but
	# parenting keeps the pattern consistent with QuestSpawner.
	var l := _label_at(Vector2(0, -22), npc_name)
	n.add_child(l)

# ---------- world ----------

func _build_floor_and_walls() -> void:
	# Verified tile coords (cross-checked against the official Ninja Adventure
	# Godot 4 reference project):
	#   • TilesetFloor.png  — interior fill. Pure plain grass at (11, 12);
	#                         decorated variants at (12, 12) and (13, 12).
	#   • TilesetField.png  — edge/corner ring. Each biome's 3×3 panel has
	#                         border tiles at (0..2, 6..8). We use the dark
	#                         green grass panel at row 6-8.
	# No bg ColorRect — the tilemap covers every cell, so a flat green behind
	# them just produces the "plain green" look the player sees through gaps
	# when nothing decorates a cell.

	var ts := TileSet.new()
	ts.tile_size = Vector2i(TILE, TILE)
	# Source 0: TilesetFloor — interior grass fill. The reference project
	# (NinjaAdventure/content/map/map_village.tscn) sprinkles tuft/flower
	# variants liberally; we want the floor to look textured, not flat.
	var floor_src := TileSetAtlasSource.new()
	floor_src.texture = load("res://assets/tilesets/TilesetFloor.png")
	floor_src.texture_region_size = Vector2i(TILE, TILE)
	# Plain grass + small grass-blade sprinkles. The (12,12)/(13,12)
	# variants have heavy Y-shaped tufts that read as trees at our zoom,
	# so we use only (14,12) and (15,12) — sparse little blade marks —
	# at low density. Most cells are plain.
	var grass_plain := Vector2i(11, 12)
	var grass_variants: Array[Vector2i] = [
		Vector2i(14, 12), Vector2i(15, 12),
	]
	floor_src.create_tile(grass_plain)
	for c in grass_variants:
		floor_src.create_tile(c)
	var floor_src_id := ts.add_source(floor_src)
	# Source 1: TilesetField — edge/corner ring
	var edge_src := TileSetAtlasSource.new()
	edge_src.texture = load("res://assets/tilesets/TilesetField.png")
	edge_src.texture_region_size = Vector2i(TILE, TILE)
	var nw := Vector2i(0, 6); var nn := Vector2i(1, 6); var ne := Vector2i(2, 6)
	var ww := Vector2i(0, 7);                            var ee := Vector2i(2, 7)
	var sw := Vector2i(0, 8); var ss := Vector2i(1, 8); var se := Vector2i(2, 8)
	for c in [nw, nn, ne, ww, ee, sw, ss, se]:
		edge_src.create_tile(c)
	var edge_src_id := ts.add_source(edge_src)

	var floor := TileMapLayer.new()
	floor.tile_set = ts
	for y in H:
		for x in W:
			# Border ring uses TilesetField source.
			if x == 0 and y == 0:
				floor.set_cell(Vector2i(x, y), edge_src_id, nw)
			elif x == W - 1 and y == 0:
				floor.set_cell(Vector2i(x, y), edge_src_id, ne)
			elif x == 0 and y == H - 1:
				floor.set_cell(Vector2i(x, y), edge_src_id, sw)
			elif x == W - 1 and y == H - 1:
				floor.set_cell(Vector2i(x, y), edge_src_id, se)
			elif y == 0:
				floor.set_cell(Vector2i(x, y), edge_src_id, nn)
			elif y == H - 1:
				floor.set_cell(Vector2i(x, y), edge_src_id, ss)
			elif x == 0:
				floor.set_cell(Vector2i(x, y), edge_src_id, ww)
			elif x == W - 1:
				floor.set_cell(Vector2i(x, y), edge_src_id, ee)
			else:
				# 85% plain green, 15% subtle blade sprinkles for texture.
				var pick: Vector2i = grass_plain
				if randf() < 0.15:
					pick = grass_variants[randi() % grass_variants.size()]
				floor.set_cell(Vector2i(x, y), floor_src_id, pick)
	level_root.add_child(floor)

	# (no scattered nature props — they read as alien blobs at zoom)
	# Walls: thin StaticBody2D rectangles around the perimeter
	var walls := StaticBody2D.new()
	walls.collision_layer = 1 << 0
	walls.collision_mask = 0
	level_root.add_child(walls)
	var wall_thickness := 8
	# top
	_add_wall(walls, Vector2(W * TILE / 2.0, -wall_thickness / 2.0), Vector2(W * TILE, wall_thickness))
	# bottom
	_add_wall(walls, Vector2(W * TILE / 2.0, H * TILE + wall_thickness / 2.0), Vector2(W * TILE, wall_thickness))
	# left
	_add_wall(walls, Vector2(-wall_thickness / 2.0, H * TILE / 2.0), Vector2(wall_thickness, H * TILE))
	# right
	_add_wall(walls, Vector2(W * TILE + wall_thickness / 2.0, H * TILE / 2.0), Vector2(wall_thickness, H * TILE))

	# (combat-arena pen and other Phase-1 sandbox geometry removed —
	# the world only contains what the LLM bundle places.)

func _scatter_nature_props(count: int) -> void:
	var nature_path := "res://assets/tilesets/TilesetNature.png"
	if not ResourceLoader.exists(nature_path):
		return
	var tex: Texture2D = load(nature_path)
	# A few hand-picked atlas regions: tufts of grass + small flowers in
	# the upper-mid rows of TilesetNature (16x16 cells at these coords).
	var props := [
		Vector2i(0, 6), Vector2i(1, 6), Vector2i(2, 6),    # grass tufts
		Vector2i(0, 7), Vector2i(1, 7), Vector2i(2, 7),    # small flowers
	]
	for i in count:
		var spr := Sprite2D.new()
		var atlas := AtlasTexture.new()
		atlas.atlas = tex
		var coord: Vector2i = props[randi() % props.size()]
		atlas.region = Rect2(coord.x * TILE, coord.y * TILE, TILE, TILE)
		spr.texture = atlas
		spr.centered = false
		# Inset 2 tiles from the edges so props don't sit under walls.
		spr.position = Vector2(
			randi_range(2, W - 3) * TILE,
			randi_range(2, H - 3) * TILE
		)
		level_root.add_child(spr)

func _add_wall(parent: StaticBody2D, center: Vector2, size: Vector2) -> void:
	var s := CollisionShape2D.new()
	var r := RectangleShape2D.new()
	r.size = size
	s.shape = r
	s.position = center
	parent.add_child(s)

# ---------- spawns ----------

func _spawn_player() -> void:
	player = Player.new()
	player.character_name = "Knight"
	# Spawn coords approximate the reference NinjaAdventure village's
	# NinjaBlue local-to-Tilemap position (56, 53) plus the Tilemap's
	# (8, -5) offset, giving world (64, 48) — central market square.
	player.position = Vector2(64, 48)
	player.request_interact.connect(_on_player_interact)
	add_child(player)
	# Hand the player a starter sword. Without a weapon equipped,
	# Player._start_attack() returns before spawning a damage Hitbox,
	# making enemies invulnerable to the swing animation.
	player.inventory.add("sword", 1)

func _spawn_item_garden() -> void:
	# NW corner
	var ids := ["sword","stone","branch","feather","grass","gem_red","gem_green","key_gold","apple","potion_red","letter","book","fish","honey","meat","pickaxe","axe"]
	var origin := Vector2(2 * TILE, 2 * TILE)
	var label := _label_at(origin + Vector2(0, -10), "Item garden")
	level_root.add_child(label)
	var i := 0
	for id in ids:
		var x := i % 4
		var y := i / 4
		var pos := origin + Vector2(x * 18, y * 18)
		ItemPickup.spawn(level_root, id, 1, pos)
		i += 1

func _spawn_combat_arena() -> void:
	# SE corner — three enemies, one of each type
	var ox := (W - 12) * TILE + 24
	var oy := (H - 10) * TILE + 30

	var slime := Enemy.new()
	slime.enemy_type = "Slime"
	slime.loot_table = ["grass", "gem_green"]
	slime.position = Vector2(ox, oy)
	level_root.add_child(slime)

	var skull := Enemy.new()
	skull.enemy_type = "Skull"
	skull.loot_table = ["coin_silver", "coin_gold"]
	skull.move_speed = 32.0
	skull.position = Vector2(ox + 50, oy + 20)
	level_root.add_child(skull)

	var bat := Enemy.new()
	bat.enemy_type = "BlueBat"
	bat.loot_table = ["feather"]
	bat.move_speed = 50.0
	bat.position = Vector2(ox + 30, oy + 60)
	level_root.add_child(bat)

	level_root.add_child(_label_at(Vector2((W - 12) * TILE + 80, (H - 10) * TILE - 8), "Combat arena (gap above)"))

func _spawn_drop_zone_sign() -> void:
	var ox := 3 * TILE
	var oy := (H - 6) * TILE
	level_root.add_child(_label_at(Vector2(ox, oy), "Drop zone (Q)"))

func _spawn_chest() -> void:
	var ch := Chest.new()
	ch.npc_name = "Chest"
	ch.contents = [{"id":"coin_gold","count":3},{"id":"key_gold","count":1}]
	ch.dialog_lines = ["A wooden chest. It smells like coins."]
	ch.position = Vector2(W * TILE / 2.0, (H - 3) * TILE)
	level_root.add_child(ch)
	level_root.add_child(_label_at(ch.position + Vector2(0, -22), "Chest"))

func _label_at(pos: Vector2, text: String) -> Control:
	var l := Label.new()
	l.text = text
	l.position = pos - Vector2(text.length() * 3.0, 0)
	l.add_theme_color_override("font_color", Color(1, 1, 1))
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0))
	l.add_theme_constant_override("outline_size", 2)
	l.add_theme_font_size_override("font_size", 8)
	return l

# ---------- camera/hud/dialog ----------

func _setup_camera() -> void:
	# Room-by-room camera matching the reference NinjaAdventure project.
	# Grid cell = 320×176 (the village's room dimensions). Viewport is
	# 640×352 with zoom 2, so visible area exactly fills one cell.
	camera = CameraGrid.new()
	camera.zoom = Vector2(2, 2)
	camera.grid_size = Vector2(320, 176)
	camera.transition_time = 0.8
	# Clamp camera to the village's tile bounds so it never reveals void
	# beyond the map. Bounds were measured by parsing tile_data:
	# tiles span x=[-27,12] y=[-15,18] -> world px (×16) including the
	# Tilemap+Map node offsets (8,-5)+(8,8) = (16,3).
	camera.limit_left = -432 + 16
	camera.limit_right = 208 + 16 + 16
	camera.limit_top = -240 + 3
	camera.limit_bottom = 304 + 3 + 16
	camera.target = player
	level_root.add_child(camera)
	camera.teleport_to(player.global_position)
	camera.make_current()
	# Perimeter walls so the player can't walk off the map either.
	_add_world_walls()

# Thin invisible StaticBody2D rectangles ringing the village bounds.
func _add_world_walls() -> void:
	var walls := StaticBody2D.new()
	walls.collision_layer = 1 << 0
	level_root.add_child(walls)
	var t: int = 16   # wall thickness
	var L := -432 + 16
	var R := 208 + 16 + 16
	var T := -240 + 3
	var B := 304 + 3 + 16
	var w := R - L
	var h := B - T
	var cx := (L + R) * 0.5
	var cy := (T + B) * 0.5
	_add_wall(walls, Vector2(cx,    T - t * 0.5),   Vector2(w + t * 2, t))   # top
	_add_wall(walls, Vector2(cx,    B + t * 0.5),   Vector2(w + t * 2, t))   # bottom
	_add_wall(walls, Vector2(L - t * 0.5, cy),       Vector2(t,         h + t * 2))   # left
	_add_wall(walls, Vector2(R + t * 0.5, cy),       Vector2(t,         h + t * 2))   # right

func _setup_hud() -> void:
	hud = Hud.new()
	add_child(hud)
	hud.bind_player(player)
	hud.toast("WASD move · J/Space attack · E interact · Q drop · 1-9 select", 4.0)

func _setup_quest_log() -> void:
	QuestManager.bind_player(player)
	quest_log = QuestLog.new()
	add_child(quest_log)

func _setup_quest_agent() -> void:
	quest_agent = QuestGenAgent.new()
	add_child(quest_agent)
	quest_agent.progress.connect(_on_agent_progress)

func _on_agent_progress(stage: String, detail: String) -> void:
	hud.toast("[%s] %s" % [stage, detail], 1.5)

# Names of all NPCs spawned by any active branching quest's bundle.
# Walks level_root for NPC instances that lack quest_giver_kind meta
# (those are the LLM-spawned ones, not our hand-placed givers).
func _bundle_npc_names() -> Array:
	var out: Array = []
	for child in level_root.get_children():
		if child is NPC and not child.has_meta("quest_giver_kind"):
			out.append((child as NPC).npc_name)
	return out

func _find_npc_by_name(name: String) -> NPC:
	for child in level_root.get_children():
		if child is NPC and (child as NPC).npc_name == name:
			return child
	return null

# Simple-quest flow per quest-giver NPC.
# State stored on the NPC's `memory` dict:
#   memory.quest_id     — id of the quest this NPC has issued (if any)
#   memory.quest_state  — "active" | "complete" (else not issued yet)
# The first interaction triggers an LLM generation call. Subsequent
# interactions branch on quest_state.
var _generating_for: NPC = null

func _handle_quest_giver(npc: NPC) -> void:
	# Concurrency guard: HTTPRequest can only run one call at a time, and
	# a second player-interact during generation overlapped requests in
	# the logs. Block new calls until the in-flight one finishes.
	if _generating_for != null:
		dialog.show_actions(npc.npc_name,
				"Patience. %s is still thinking..." % _generating_for.npc_name,
				["Bye"])
		return
	var kind: String = String(npc.get_meta("quest_giver_kind", "fetch"))
	if kind == "two_stage":
		await _handle_two_stage(npc)
		return
	if kind == "branching":
		await _handle_branching(npc)
		return
	var qid: String = String(npc.memory.get("quest_id", ""))
	if qid == "":
		# First interaction — generate.
		_generating_for = npc
		dialog.show_actions(npc.npc_name, "Hold on, traveler — let me think...", [])
		hud.toast("[%s] writing your quest..." % npc.npc_name, 4.0)
		var result: Dictionary = await quest_agent.generate_simple(
				npc.npc_name, npc.role, kind)
		_generating_for = null
		if not result.get("ok", false):
			var err: String = String(result.get("error", "unknown"))
			dialog.show_actions(npc.npc_name,
					"Words fail me — try again. (%s)" % err, ["Bye"])
			print("[main] simple-quest fail for %s: %s" % [npc.npc_name, err])
			return
		var q: Dictionary = result.quest
		_register_simple_quest(npc, q)
		_spawn_quest_targets(q, npc.global_position)
		var intro: String = String(q.get("dialog", {}).get("intro",
				String(q.get("description", "I have a task for you."))))
		dialog.show_actions(npc.npc_name, intro, ["Accept"])
		return
	# Quest already issued — check status.
	var quest := QuestManager.get_quest(qid)
	if quest != null and quest.status == Quest.Status.COMPLETED:
		var line: String = String(npc.memory.get("dialog_complete",
				"Many thanks. Take this with my gratitude."))
		dialog.show_actions(npc.npc_name, line, ["Bye"])
		_grant_simple_rewards(npc)
		npc.memory["quest_state"] = "complete"
		return
	# Active. Offer Give so the player can hand over the requested item.
	var line2: String = String(npc.memory.get("dialog_active",
			"Still on the way? Hurry."))
	dialog.show_actions(npc.npc_name, line2, ["Give", "Bye"])

# Wanderer-as-orchestrator flow. The Wanderer is the single source of
# narrative truth: he gives the first chapter, decides whether each
# subsequent player-talk yields a continuation or a closing, and never
# auto-fails on unexpected actions.
#
# State machine on `npc.memory`:
#   wanderer_state       : "idle" | "active" | "closing"
#   orchestration_count  : int  (number of continuations so far; capped)
#   quest_id_branching   : id of the active chapter's Quest (for replace)

const MAX_ORCHESTRATIONS := 5

func _handle_branching(npc: NPC) -> void:
	var state: String = String(npc.memory.get("wanderer_state", "idle"))
	if state == "idle":
		dialog.show_actions(npc.npc_name,
				"I have a tale brewing. Will you hear it?", ["Yes", "Bye"])
		return
	if state == "closing":
		dialog.show_actions(npc.npc_name, "(reading the threads...)", [])
		return
	# state == "active"
	if QuestManager.action_ledger.is_empty():
		dialog.show_actions(npc.npc_name,
				"You've done nothing of consequence. Walk, act, then return to me.",
				["Bye"])
		return
	var n: int = int(npc.memory.get("orchestration_count", 0))
	var remaining: int = max(0, MAX_ORCHESTRATIONS - n)
	dialog.show_actions(npc.npc_name,
			"Tell me what's happened. (%d chapters left)" % remaining,
			["Report", "Bye"])

# Generates the FIRST chapter from a fresh Wanderer talk.
func _kickoff_first_chapter(npc: NPC) -> void:
	if _generating_for != null:
		dialog.show_actions(npc.npc_name, "Wait — another tale is still being spun.", ["Bye"])
		return
	_generating_for = npc
	dialog.show_actions(npc.npc_name, "(weaving the opening threads...)", [])
	hud.toast("[%s] weaving the first chapter..." % npc.npc_name, 6.0)
	var r: Dictionary = await quest_agent.generate_branching(npc.npc_name, npc.role)
	_generating_for = null
	if not r.get("ok", false):
		var err: String = String(r.get("error", "unknown"))
		dialog.show_actions(npc.npc_name,
				"Words won't come tonight. (%s)" % err, ["Bye"])
		print("[main] branching fail for %s: %s" % [npc.npc_name, err])
		return
	_install_chapter(npc, r.bundle, "✦ %s ✦")

# Wanderer-talk after the player has acted: orchestration LLM call.
func _orchestrate_next_chapter(npc: NPC) -> void:
	if _generating_for != null:
		dialog.show_actions(npc.npc_name, "Patience — the threads are still moving.", ["Bye"])
		return
	var n: int = int(npc.memory.get("orchestration_count", 0))
	var remaining: int = max(0, MAX_ORCHESTRATIONS - n)
	_generating_for = npc
	npc.memory["wanderer_state"] = "closing"  # locked while in flight
	dialog.show_actions(npc.npc_name, "(reading the threads...)", [])
	var prev := _summarize_active_quest()
	var current := _bundle_npc_names()
	print("[orchestrator] talk #%d  ledger_size=%d  remaining=%d  current_npcs=%s" % [
			n + 1, QuestManager.action_ledger.size(), remaining, str(current)])
	print("[orchestrator] prev_quest title='%s'  branches=%d" % [
			prev.get("title",""), (prev.get("branches", []) as Array).size()])
	for entry in QuestManager.action_ledger:
		print("  ledger: ", entry)
	var r: Dictionary = await quest_agent.generate_orchestration(
			prev, QuestManager.action_ledger, current, npc.npc_name, remaining)
	_generating_for = null
	if not r.get("ok", false):
		print("[orchestrator] FAIL: ", r.get("error",""))
		npc.memory["wanderer_state"] = "active"
		dialog.show_actions(npc.npc_name,
				"My sight failed me. Try again later. (%s)" % r.get("error",""),
				["Bye"])
		return
	# Hard guardrails on top of LLM judgment.
	var decision: String = String(r.decision)
	var orig_decision: String = decision
	if n >= MAX_ORCHESTRATIONS:
		decision = "complete"
	if decision == "complete" and QuestManager.action_ledger.size() < 2:
		decision = "continue"
	if decision == "continue" and not r.has("new_quest"):
		decision = "complete"   # safety: bad pack
	if decision != orig_decision:
		print("[orchestrator] decision overridden: %s -> %s" % [orig_decision, decision])
	print("[orchestrator] applying decision=%s  wanderer_dialog='%s'" % [
			decision, String(r.wanderer_dialog).substr(0, 80)])
	# Apply.
	if decision == "continue":
		var new_quest: Dictionary = r.new_quest
		print("[orchestrator] new chapter: title='%s'  npcs=%d  branches=%d" % [
				String(new_quest.get("quest", {}).get("title","?")),
				(new_quest.get("npcs", []) as Array).size(),
				(new_quest.get("quest", {}).get("branches", []) as Array).size()])
		_close_active_quest("orchestrator_continuation")
		_install_chapter(npc, new_quest, String(r.wanderer_dialog))
		npc.memory["orchestration_count"] = n + 1
	else:
		_finish_orchestrator_quest(npc, String(r.wanderer_dialog), r.get("rewards", []))

func _install_chapter(npc: NPC, bundle: Dictionary, intro_text: String) -> void:
	var quest_dict: Dictionary = bundle.get("quest", {})
	# Stamp the orchestrator-managed flag so QuestSpawner sets it on the
	# registered Quest, disabling auto-completion.
	quest_dict["orchestrator_managed"] = true
	bundle["quest"] = quest_dict
	QuestSpawner.spawn(bundle, level_root, player, _all_quest_givers())
	npc.memory["wanderer_state"] = "active"
	var qid: String = String(quest_dict.get("id",""))
	if qid != "":
		_quest_giver_for[qid] = npc.npc_name
		npc.memory["quest_id_branching"] = qid
	var qtitle: String = String(quest_dict.get("title","A tale"))
	var qdesc: String = String(quest_dict.get("description",""))
	var spawned: Array = []
	for n2 in bundle.get("npcs", []):
		spawned.append(String((n2 as Dictionary).get("npc_name","?")))
	# Collect starting items the bundle scattered for the player so the
	# Wanderer's intro mentions them — otherwise they look like random
	# pickups the player has to figure out.
	var starting_items: Array = []
	for it in bundle.get("items", []):
		var iid: String = String((it as Dictionary).get("id",""))
		if iid != "": starting_items.append(iid)
	var lore: String
	if intro_text == "✦ %s ✦":
		# First chapter: synthetic intro from the bundle.
		lore = "✦ %s ✦\n\n%s" % [qtitle, qdesc]
		if not spawned.is_empty():
			lore += "\n\nYou may meet: " + ", ".join(spawned) + "."
		if not starting_items.is_empty():
			lore += "\n\nTake these — they may help: " + ", ".join(starting_items) + "."
	else:
		# Continuation: Wanderer's own LLM-authored line plus the new title.
		lore = intro_text + "\n\n— Next chapter: %s —\n%s" % [qtitle, qdesc]
		if not spawned.is_empty():
			lore += "\n\nNow walking the world: " + ", ".join(spawned) + "."
		if not starting_items.is_empty():
			lore += "\n\nFresh tools left for you: " + ", ".join(starting_items) + "."
	print("[main] chapter installed: '%s' npcs=%s items=%s" % [
			qtitle, str(spawned), str(starting_items)])
	hud.toast("Chapter accepted: %s" % qtitle, 4.0)
	dialog.show_actions(npc.npc_name, lore, ["Accept"])

# Closes whichever quest the Wanderer is currently shepherding. Clears
# the giver-map entry for the closed quest so the next chapter starts
# with a clean record.
func _close_active_quest(branch_label: String) -> void:
	# Single Wanderer assumption: the only branching giver in play. Use
	# whichever qid maps from this giver in the registry.
	var stale_qids: Array = []
	for k in _quest_giver_for.keys():
		stale_qids.append(String(k))
	for qid in stale_qids:
		var q := QuestManager.get_quest(qid)
		if q != null and q.status == Quest.Status.ACTIVE:
			q.status = Quest.Status.COMPLETED
			q.completed_branch_id = branch_label
			QuestManager.active_quests.erase(q)
			QuestManager.completed_quests.append(q)
			QuestManager.quest_completed.emit(q)
		_quest_giver_for.erase(qid)

func _finish_orchestrator_quest(npc: NPC, line: String, rewards: Array) -> void:
	_close_active_quest("orchestrator_closing")
	for r in rewards:
		if not (r is Dictionary): continue
		var iid: String = String((r as Dictionary).get("item_id",""))
		var count: int = int((r as Dictionary).get("count", 1))
		if ItemDB.has(iid) and count > 0:
			player.inventory.add(iid, count)
			hud.toast("+%d %s" % [count, iid], 2.0)
	QuestManager.clear_ledger()
	npc.memory["wanderer_state"] = "idle"
	npc.memory["orchestration_count"] = 0
	npc.memory.erase("quest_id_branching")
	# Drop the spawned NPCs/items + any stranded floating Labels so the
	# next quest starts on a clean slate. Labels are now child of their
	# NPC; this Label sweep just defends against regressions.
	for child in level_root.get_children():
		if child is NPC and not child.has_meta("quest_giver_kind"):
			child.queue_free()
		elif child is ItemPickup:
			child.queue_free()
		elif child is Label:
			child.queue_free()
	for k in _quest_giver_for.keys():
		_quest_giver_for.erase(k)
	dialog.show_actions(npc.npc_name, line, ["Bye"])

func _summarize_active_quest() -> Dictionary:
	if QuestManager.active_quests.is_empty():
		return {}
	var q: Quest = QuestManager.active_quests[0]
	var brs: Array = []
	for b in q.branches:
		brs.append({"id": b.id, "description": b.description})
	return {"title": q.title, "description": q.description, "branches": brs}

# Returns the set of hand-placed quest-givers so QuestSpawner's wipe step
# preserves them when installing the bundle's LLM-spawned NPCs.
func _all_quest_givers() -> Array:
	var out: Array = []
	for child in level_root.get_children():
		if child is NPC and child.has_meta("quest_giver_kind"):
			out.append(child)
	return out

# Two-stage quest flow.
# memory keys used:
#   stage          - 0 (no quest) | 1 | "choosing" | 2 | "done"
#   quest_id       - the currently-active quest id
#   stage1_summary - one-line description of what the player did in stage 1
#                    (passed to the LLM when generating stage 2 so the
#                     model can reference the context)
func _handle_two_stage(npc: NPC) -> void:
	var stage: Variant = npc.memory.get("stage", 0)
	# State 0: no quest yet — generate stage 1.
	if stage == 0:
		_generating_for = npc
		dialog.show_actions(npc.npc_name, "Hold... let me see what fate wants.", [])
		hud.toast("[%s] reading the threads..." % npc.npc_name, 4.0)
		var r1: Dictionary = await quest_agent.generate_stage1(npc.npc_name, npc.role)
		_generating_for = null
		if not r1.get("ok", false):
			dialog.show_actions(npc.npc_name,
					"The threads are tangled. Return when the veil clears. (%s)" % r1.get("error",""), ["Bye"])
			return
		var q: Dictionary = r1.quest
		_register_simple_quest(npc, q)
		_spawn_quest_targets(q, npc.global_position)
		npc.memory["stage"] = 1
		npc.memory["stage1_summary"] = "%s — %s" % [
				String(q.get("title","")), String(q.get("description",""))]
		dialog.show_actions(npc.npc_name, String(q.get("dialog",{}).get("intro",
				q.get("description","Bring it to me."))), ["Accept"])
		return
	# State 1: stage-1 quest active or completed.
	if stage == 1:
		var qid: String = String(npc.memory.get("quest_id",""))
		var quest := QuestManager.get_quest(qid)
		if quest != null and quest.status == Quest.Status.COMPLETED:
			# Time for the moral choice.
			npc.memory["stage"] = "choosing"
			dialog.show_actions(npc.npc_name,
					"Now — what will you do with what we now hold? "
					+ "Use it as we agreed... or twist it for yourself.",
					["Path of Honor", "Path of Greed"])
			return
		# Stage 1 still active — usual Give/Bye.
		var line2: String = String(npc.memory.get("dialog_active",
				"The veil holds. Hurry."))
		dialog.show_actions(npc.npc_name, line2, ["Give", "Bye"])
		return
	# State "choosing": player should still be picking — prompt again.
	if stage == "choosing":
		dialog.show_actions(npc.npc_name, "Choose. The threads grow impatient.",
				["Path of Honor", "Path of Greed"])
		return
	# State 2: stage-2 quest active or completed.
	if stage == 2:
		var qid2: String = String(npc.memory.get("quest_id",""))
		var quest2 := QuestManager.get_quest(qid2)
		if quest2 != null and quest2.status == Quest.Status.COMPLETED:
			var line: String = String(npc.memory.get("dialog_complete",
					"It is finished. The threads close around you."))
			dialog.show_actions(npc.npc_name, line, ["Bye"])
			_grant_simple_rewards(npc)
			npc.memory["stage"] = "done"
			return
		var line3: String = String(npc.memory.get("dialog_active",
				"The path is yours to walk. Return when it ends."))
		var actions: Array = ["Give", "Bye"]
		dialog.show_actions(npc.npc_name, line3, actions)
		return
	# Done.
	dialog.show_actions(npc.npc_name,
			"Our threads have parted, traveler. Walk well.", ["Bye"])

# Generates stage 2 once the player picks a path. Called from the dialog
# action handler when the user clicks PathHonor or PathGreed.
func _start_stage_two(npc: NPC, path: String) -> void:
	if _generating_for != null:
		dialog.show_actions(npc.npc_name,
				"Patience — another's thread is still spinning.", ["Bye"])
		return
	_generating_for = npc
	dialog.show_actions(npc.npc_name,
			"Then so it is. I weave the next path...", [])
	hud.toast("[%s] weaving stage 2 (%s)" % [npc.npc_name, path], 5.0)
	var summary: String = String(npc.memory.get("stage1_summary",""))
	var r: Dictionary = await quest_agent.generate_stage2(
			npc.npc_name, npc.role, summary, path)
	_generating_for = null
	if not r.get("ok", false):
		dialog.show_actions(npc.npc_name,
				"The threads frayed. Try again. (%s)" % r.get("error",""), ["Bye"])
		# Reset to choosing so the player can retry.
		npc.memory["stage"] = "choosing"
		return
	var q: Dictionary = r.quest
	# Clear the previous quest_id so _register_simple_quest installs the new one cleanly.
	npc.memory["quest_id"] = ""
	npc.memory["rewarded"] = false
	_register_simple_quest(npc, q)
	_spawn_quest_targets(q, npc.global_position)
	npc.memory["stage"] = 2
	dialog.show_actions(npc.npc_name, String(q.get("dialog",{}).get("intro",
			q.get("description","Walk this new path."))), ["Accept"])

# Wraps the simple-quest dict (single objective shape) into the standard
# Quest dict the QuestManager expects (objectives array), then registers
# both the quest and the per-NPC dialog snippets.
func _register_simple_quest(npc: NPC, q: Dictionary) -> void:
	var obj: Dictionary = q.get("objective", {})
	# Force `give` objectives to point at THIS NPC, regardless of what
	# the LLM emitted — the model sometimes uses a generic role name
	# ("Farmer") instead of the actual `npc_name`.
	if String(obj.get("type","")) == "give":
		var params: Dictionary = obj.get("params", {})
		params["npc_name"] = npc.npc_name
		obj["params"] = params
		q["objective"] = obj
	var quest_dict: Dictionary = {
		"id": String(q.get("id", "simple_%s_%d" % [npc.npc_name, randi()])),
		"title": String(q.get("title", "A small task")),
		"description": String(q.get("description", "")),
		"sequential": false,
		"objectives": [obj] if not obj.is_empty() else [],
		"rewards": q.get("rewards", []),
		"branches": [],
		"fail_conditions": [],
	}
	QuestManager.add_quest_from_dict(quest_dict)
	npc.memory["quest_id"] = quest_dict.id
	npc.memory["quest_state"] = "active"
	var d: Dictionary = q.get("dialog", {})
	npc.memory["dialog_active"] = String(d.get("active", "Still working on it?"))
	npc.memory["dialog_complete"] = String(d.get("complete", "Well done."))
	hud.toast("Quest accepted: %s" % quest_dict.title, 3.0)

# After a simple quest is registered, materialise its target(s) into the
# world AROUND THE QUEST-GIVER. The giver is by definition standing in
# walkable terrain (the player just talked to them), so spreading targets
# in a short ring around them keeps everything inside the playable area
# instead of in walls or buildings.
func _spawn_quest_targets(q: Dictionary, origin: Vector2) -> void:
	var obj: Dictionary = q.get("objective", {})
	var t: String = String(obj.get("type", ""))
	var required: int = int(obj.get("required", 1))
	var p: Dictionary = obj.get("params", {})
	# Item radius: 24-56 px (1.5–3.5 tiles).  Enemy radius: 48-96 px.
	# Both stay within the same "room" so the player can find them after
	# accepting without walking off-map.
	match t:
		"give", "collect":
			var iid: String = String(p.get("item_id", ""))
			if iid == "" or not ItemDB.has(iid):
				return
			# Tight ring (16-32 px = 1-2 tiles) so items land on the same
			# tile the giver is standing on (which we know is walkable).
			var positions := _ring_spots(origin, required + 1, 16.0, 32.0)
			for pos in positions:
				ItemPickup.spawn(level_root, iid, 1, pos)
		"kill_enemy":
			var etype: String = String(p.get("enemy_type", "Slime"))
			var positions := _ring_spots(origin, required, 48.0, 96.0)
			for pos in positions:
				var e := Enemy.new()
				e.enemy_type = etype
				e.position = pos
				match etype:
					"BlueBat":
						e.move_speed = 50.0
						e.loot_table = ["feather"]
					"Skull":
						e.move_speed = 32.0
						e.loot_table = ["coin_silver", "coin_gold"]
					_:
						e.loot_table = ["grass", "gem_green"]
				level_root.add_child(e)

# Distributes `n` positions evenly around `origin` at varying radii. Avoids
# stacking by giving each spawn its own angle slice.
func _ring_spots(origin: Vector2, n: int, r_min: float, r_max: float) -> Array[Vector2]:
	var out: Array[Vector2] = []
	if n <= 0: return out
	for i in n:
		var angle: float = (TAU * i) / float(n) + randf_range(-0.3, 0.3)
		var radius: float = randf_range(r_min, r_max)
		out.append(origin + Vector2(cos(angle), sin(angle)) * radius)
	return out

func _grant_simple_rewards(npc: NPC) -> void:
	if npc.memory.get("rewarded", false):
		return
	npc.memory["rewarded"] = true
	var qid: String = String(npc.memory.get("quest_id", ""))
	var quest := QuestManager.get_quest(qid)
	if quest == null: return
	for r in quest.rewards:
		var iid: String = String(r.get("item_id",""))
		var count: int = int(r.get("count", 1))
		if ItemDB.has(iid) and count > 0:
			player.inventory.add(iid, count)
			hud.toast("+%d %s" % [count, iid], 2.0)

func _kickoff_initial_quest() -> void:
	# Pick a random premise from the pool every run so each playthrough
	# starts with a different setup. The pool intentionally avoids the
	# Elder/Bandit/gem story used as the few-shot fixture.
	_current_premise = LlmPrompts.pick_premise()
	print("[main] kickoff premise: ", _current_premise)
	hud.toast("Generating quest...", 4.0)
	var result: Dictionary = await quest_agent.generate(_current_premise)
	if not result.get("ok", false):
		hud.toast("Generation failed: " + String(result.get("error", "")), 5.0)
		return
	var bundle: Dictionary = result.bundle
	QuestSpawner.spawn(bundle, level_root, player, null)
	if result.get("fallback", false):
		hud.toast("LLM failed — using fallback fixture", 3.0)
	else:
		hud.toast("Quest ready: " + String(bundle.get("quest", {}).get("title","")), 3.0)

func _setup_dialog() -> void:
	dialog = DialogBox.new()
	dialog.visible = false
	dialog.action_chosen.connect(_on_dialog_action)
	dialog.item_chosen.connect(_on_dialog_item)
	dialog.choice_chosen.connect(_on_dialog_choice)
	dialog.closed.connect(_on_dialog_closed)
	add_child(dialog)

# ---------- dialog flow ----------

func _on_player_interact(target: Node) -> void:
	if dialog.visible: return
	_current_npc = target
	_dialog_state = "menu"
	_dialog_node_id = ""
	_set_player_locked(true)
	# Quest-giver NPCs route to the simple-quest LLM flow: ask once,
	# generate, give intro/active/complete dialog as state advances.
	if target is NPC and target.has_meta("quest_giver_kind"):
		await _handle_quest_giver(target as NPC)
		return
	# If the NPC has a rich dialog tree, jump straight into it.
	if target is NPC and not (target as NPC).dialog_tree.is_empty():
		var npc := target as NPC
		var start_id := _resolve_start_node(npc)
		_open_dialog_node(start_id)
		return
	var line: String = ""
	if "dialog_lines" in target and not target.dialog_lines.is_empty():
		line = target.dialog_lines[randi() % target.dialog_lines.size()]
	var actions: Array = []
	if target.is_in_group("chest"):
		actions = ["Take"]
	elif target is NPC:
		actions = ["Talk", "Give", "Take"]
	dialog.show_actions(target.get("npc_name"), line, actions)

func _on_dialog_action(action: String) -> void:
	print("[main] _on_dialog_action: '", action, "' npc=", _current_npc)
	if _current_npc == null:
		# Don't silently swallow clicks — close so the player isn't stuck.
		dialog.close_dialog()
		return
	match action:
		"Talk":
			var line: String = _current_npc.dialog_lines[randi() % _current_npc.dialog_lines.size()]
			dialog.show_actions(_current_npc.npc_name, line, ["Talk"])
			Game.npc_interacted.emit(_current_npc.npc_name, "talk")
		"Give":
			_dialog_state = "give"
			dialog.show_inventory_picker(_current_npc.npc_name + " — give which?", "Pick an item to give", player.inventory)
		"Take":
			_dialog_state = "take"
			dialog.show_inventory_picker(_current_npc.npc_name + " — take which?", "Pick an item to take", _current_npc.inventory)
		"Accept", "Bye":
			dialog.close_dialog()
		"Yes":
			# Wanderer kickoff: first chapter generation.
			if _current_npc is NPC and _current_npc.has_meta("quest_giver_kind") \
					and String(_current_npc.get_meta("quest_giver_kind")) == "branching":
				_kickoff_first_chapter(_current_npc as NPC)
		"Report":
			# Wanderer orchestration: read the action ledger, generate
			# a continuation chapter or a closing.
			if _current_npc is NPC and _current_npc.has_meta("quest_giver_kind") \
					and String(_current_npc.get_meta("quest_giver_kind")) == "branching":
				_orchestrate_next_chapter(_current_npc as NPC)
		"Path of Honor":
			if _current_npc is NPC and _current_npc.has_meta("quest_giver_kind") \
					and String(_current_npc.get_meta("quest_giver_kind")) == "two_stage":
				_start_stage_two(_current_npc as NPC, LlmPrompts.TWO_STAGE_PATH_A)
		"Path of Greed":
			if _current_npc is NPC and _current_npc.has_meta("quest_giver_kind") \
					and String(_current_npc.get_meta("quest_giver_kind")) == "two_stage":
				_start_stage_two(_current_npc as NPC, LlmPrompts.TWO_STAGE_PATH_B)
		_:
			# Anything else (buttons we didn't pre-register) just closes
			# the dialog so the player isn't stuck.
			dialog.close_dialog()

func _on_dialog_item(slot_idx: int) -> void:
	if _current_npc == null: return
	if _dialog_state == "give":
		var taken: Dictionary = player.inventory.remove_one(slot_idx)
		if not taken.is_empty():
			_current_npc.inventory.add(taken.id, 1)
			Game.npc_interacted.emit(_current_npc.npc_name, "give:" + taken.id)
			hud.toast("Gave %s to %s" % [taken.id, _current_npc.npc_name])
	elif _dialog_state == "take":
		var taken: Dictionary = _current_npc.inventory.remove_one(slot_idx)
		if not taken.is_empty():
			player.inventory.add(taken.id, 1)
			Game.npc_interacted.emit(_current_npc.npc_name, "take:" + taken.id)
			hud.toast("Took %s from %s" % [taken.id, _current_npc.npc_name])
	dialog.close_dialog()

func _resolve_start_node(npc: NPC) -> String:
	return npc.resolve_start_node(player, _npc_index())

func _npc_index() -> Dictionary:
	var d := {}
	for n in get_tree().get_nodes_in_group("npc"):
		if "npc_name" in n:
			d[n.npc_name] = n
	return d

func _open_dialog_node(node_id: String) -> void:
	if not (_current_npc is NPC):
		dialog.close_dialog()
		return
	var npc := _current_npc as NPC
	if not npc.dialog_tree.has(node_id):
		dialog.close_dialog()
		return
	_dialog_state = "tree"
	_dialog_node_id = node_id
	var node: Dictionary = npc.dialog_tree[node_id]
	var visible := npc.visible_choices(node_id, player, _npc_index())
	# Always offer Give/Take so the player can transfer items to/from a
	# dialog-tree NPC even when the writer didn't author item-transfer
	# choices. main._on_dialog_action handles Give/Take by opening the
	# inventory picker against the current NPC.
	dialog.show_node(npc.npc_name, node, visible, ["Give", "Take"])
	# (prefetch disabled — concurrent expand calls collide on the single
	# HTTPRequest in the LLM client and produce noisy errors. Lazy
	# expansion happens on-demand when the player picks a choice.)

func _prefetch_expansions(npc: NPC, node_id: String, node: Dictionary) -> void:
	if quest_agent == null:
		return
	for c in node.get("choices", []):
		if String(c.get("next","")) == "__expand__":
			var ctx := _build_expand_context(npc, node_id, c)
			# Fire-and-forget: Godot runs the coroutine; cache holds the result.
			quest_agent.expand_node(ctx)

func _build_expand_context(npc: NPC, parent_id: String, choice: Dictionary) -> Dictionary:
	var inv: Array = []
	for s in player.inventory.slots:
		if s != null:
			inv.append(s.id)
	var qtitle := ""
	var qdesc := ""
	var brs: Array = []
	if not QuestManager.active_quests.is_empty():
		var q: Quest = QuestManager.active_quests[0]
		qtitle = q.title
		qdesc = q.description
		for b in q.branches:
			brs.append("%s: %s" % [b.id, b.description])
	return {
		"premise": _current_premise,
		"npc_name": npc.npc_name,
		"npc_role": npc.role,
		"character_sheet": npc.character_sheet,
		"parent_node_id": parent_id,
		"parent_node_text": String(npc.dialog_tree.get(parent_id, {}).get("text","")),
		"choice_id": String(choice.get("id","")),
		"choice_text": String(choice.get("text","")),
		"choice_hint": String(choice.get("next_hint","")),
		"quest_title": qtitle,
		"quest_description": qdesc,
		"branch_summaries": brs,
		"player_flags": QuestManager.global_flags.duplicate(),
		"player_inventory": inv,
	}

func _on_dialog_choice(choice: Dictionary) -> void:
	if _current_npc == null or not (_current_npc is NPC):
		return
	var npc := _current_npc as NPC
	var choice_id: String = choice.get("id", "")
	if choice_id != "":
		QuestManager.dialog_choice(npc.npc_name, choice_id)
	for action in choice.get("actions", []):
		_run_dialog_action(npc, String(action))
	# `die` action above may have queue_free'd the NPC: bail safely.
	if not is_instance_valid(_current_npc):
		dialog.close_dialog()
		return
	var nxt: Variant = choice.get("next", null)
	var nxt_str: String = String(nxt) if nxt != null else ""
	if nxt_str == "" or nxt_str == "end":
		dialog.close_dialog()
	elif nxt_str == "__expand__":
		await _expand_and_navigate(npc, choice)
	else:
		_open_dialog_node(nxt_str)

func _expand_and_navigate(npc: NPC, choice: Dictionary) -> void:
	# Show a transient "thinking" node while the agent generates.
	var spinner_node := {"text": "...", "choices": []}
	dialog.show_node(npc.npc_name, spinner_node, [])
	var ctx := _build_expand_context(npc, _dialog_node_id, choice)
	var result: Dictionary = await quest_agent.expand_node(ctx)
	var new_node: Dictionary = result.get("node", {"text":"...","choices":[]})
	# Defensive: a parse-failure fallback comes back with empty choices,
	# which collapses the dialog to just [Give]/[Take]/[Bye] and feels
	# like the conversation dies mid-sentence. Inject a "Tell me more"
	# follow-up that lazy-expands again so the player can keep pushing.
	if (new_node.get("choices", []) as Array).is_empty():
		new_node["choices"] = [{
			"id": "tell_me_more",
			"text": "Tell me more.",
			"next": "__expand__",
			"next_hint": "Continue the conversation from: " + String(new_node.get("text","")).substr(0, 80),
		}]
		print("[main] expand fallback: injected lazy 'Tell me more' (parent=%s, choice=%s)" % [
				_dialog_node_id, String(choice.get("id",""))])
	# Splice into the npc's dialog_tree under a stable id so revisits skip expansion.
	var new_id: String = "%s__%s" % [_dialog_node_id, String(choice.get("id",""))]
	npc.dialog_tree[new_id] = new_node
	choice["next"] = new_id
	# If dialog closed mid-expansion (e.g. NPC died) — bail.
	if not dialog.visible or _current_npc != npc:
		return
	_open_dialog_node(new_id)

func _run_dialog_action(npc: NPC, action: String) -> void:
	# action grammar:
	#   give_player:item_id        — NPC gives 1 to player (and removes from NPC inv if present)
	#   take_player:item_id        — Player gives 1 to NPC (only if player has it)
	#   drop_inventory             — NPC drops all items to ground
	#   set_flag:key=value         — global flag (also set on every active quest)
	#   remember:key=value         — per-NPC scratch
	#   die                        — NPC dies, drops loot
	if ":" in action:
		var parts := action.split(":", false, 1)
		var verb: String = parts[0]
		var arg: String = parts[1]
		match verb:
			"give_player":
				# Only succeeds if NPC actually has the item.
				var found := false
				for i in Inventory.SLOT_COUNT:
					var s = npc.inventory.slots[i]
					if s != null and s.id == arg:
						npc.inventory.remove_one(i)
						found = true
						break
				if found and player.inventory.add(arg, 1) == 0:
					Game.item_picked_up.emit(arg, 1)
			"take_player":
				for i in Inventory.SLOT_COUNT:
					var s = player.inventory.slots[i]
					if s != null and s.id == arg:
						player.inventory.remove_one(i)
						npc.inventory.add(arg, 1)
						Game.npc_interacted.emit(npc.npc_name, "give:" + arg)
						break
			"set_flag":
				var kv := arg.split("=", false, 1)
				if kv.size() == 2:
					QuestManager.set_flag_all_active(kv[0], kv[1])
			"remember":
				var kv2 := arg.split("=", false, 1)
				if kv2.size() == 2:
					npc.memory[kv2[0]] = kv2[1]
	else:
		match action:
			"drop_inventory":
				for i in Inventory.SLOT_COUNT:
					var s = npc.inventory.slots[i]
					if s != null:
						var off := Vector2(randf_range(-12, 12), randf_range(-12, 12))
						ItemPickup.spawn(level_root, s.id, s.count, npc.global_position + off)
						npc.inventory.slots[i] = null
				npc.inventory.changed.emit()
			"die":
				# Defer the death until after the dialog tree finishes
				# resolving — calling _die() inline queue_free()'s the NPC
				# while the dialog is still rendering choices, leaving the
				# player stuck in a conversation with a dead reference.
				hud.toast("%s has fallen." % String(npc.npc_name), 2.5)
				npc.call_deferred("_die")

func _on_dialog_closed() -> void:
	_current_npc = null
	_dialog_state = ""
	_dialog_node_id = ""
	_set_player_locked(false)

func _set_player_locked(locked: bool) -> void:
	if player == null: return
	player.set_physics_process(not locked)
	player.set_process_unhandled_input(not locked)
	if locked:
		player.velocity = Vector2.ZERO
