extends Node2D

const TILE := 16
const W := 40   # tiles
const H := 30

var player: Player
var hud: Hud
var dialog: DialogBox
var quest_log: QuestLog
var camera: Camera2D
var level_root: Node2D

var _current_npc: Node = null
var _dialog_state: String = ""   # "menu" / "give" / "take" / "tree"
var _dialog_node_id: String = ""

func _ready() -> void:
	randomize()
	level_root = Node2D.new()
	level_root.name = "Level"
	add_child(level_root)
	_build_floor_and_walls()
	_spawn_player()
	_spawn_item_garden()
	_spawn_village()
	_spawn_combat_arena()
	_spawn_drop_zone_sign()
	_spawn_chest()
	_setup_camera()
	_setup_hud()
	_setup_dialog()
	_setup_quest_log()
	_seed_sample_quests()

# ---------- world ----------

func _build_floor_and_walls() -> void:
	# A solid green ColorRect floor + a single StaticBody2D ring of walls.
	var floor := ColorRect.new()
	floor.color = Color(0.27, 0.55, 0.27)
	floor.size = Vector2(W * TILE, H * TILE)
	floor.position = Vector2.ZERO
	level_root.add_child(floor)
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

	# combat arena fence (SE corner): a 10x8 pen with a 1-tile gap in the north wall
	var pen_x := (W - 12) * TILE
	var pen_y := (H - 10) * TILE
	var pen_w := 10 * TILE
	var pen_h := 8 * TILE
	# north wall left half
	_add_wall(walls, Vector2(pen_x + pen_w * 0.25, pen_y), Vector2(pen_w * 0.4, 4))
	# north wall right half
	_add_wall(walls, Vector2(pen_x + pen_w * 0.75, pen_y), Vector2(pen_w * 0.4, 4))
	# south wall
	_add_wall(walls, Vector2(pen_x + pen_w * 0.5, pen_y + pen_h), Vector2(pen_w, 4))
	# west wall
	_add_wall(walls, Vector2(pen_x, pen_y + pen_h * 0.5), Vector2(4, pen_h))
	# east wall
	_add_wall(walls, Vector2(pen_x + pen_w, pen_y + pen_h * 0.5), Vector2(4, pen_h))

	# arena visual outline
	var pen_visual := ColorRect.new()
	pen_visual.color = Color(0.6, 0.3, 0.2, 0.25)
	pen_visual.position = Vector2(pen_x, pen_y)
	pen_visual.size = Vector2(pen_w, pen_h)
	level_root.add_child(pen_visual)

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
	player.position = Vector2(W * TILE / 2.0, H * TILE / 2.0)
	player.request_interact.connect(_on_player_interact)
	add_child(player)

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

func _spawn_village() -> void:
	# NE corner
	var ox := (W - 8) * TILE
	var oy := 3 * TILE
	level_root.add_child(_label_at(Vector2(ox, oy - 12), "Elder's hut"))

	var elder := NPC.new()
	elder.npc_name = "Elder"
	elder.character_sheet = "OldMan"
	elder.role = "elder"
	elder.max_health = 3
	# Elder carries some loot so the betrayal path actually pays off.
	elder.initial_items = [{"id":"coin_gold","count":2},{"id":"key_silver","count":1}]
	elder.position = Vector2(ox + 28, oy + 24)
	# Pick the right starting node based on quest state and what's in the
	# player's bag right now. Evaluated top-to-bottom; first match wins.
	elder.start_nodes = [
		{"node":"start_done",      "requires":{"quest:stolen_heirloom":"completed"}},
		{"node":"start_failed",    "requires":{"quest:stolen_heirloom":"failed"}},
		{"node":"start_has_gem",   "requires":{"quest:stolen_heirloom":"active", "inv:gem_red":">=1"}},
		{"node":"start_in_progress","requires":{"quest:stolen_heirloom":"active", "flag:elder_briefed":"true"}},
		{"node":"start_intro",     "requires":{"quest:stolen_heirloom":"active"}},
	]
	elder.dialog_start = "start_intro"
	elder.dialog_tree = {
		"start_intro": {
			"text": "The old man's eyes water as you approach. \"Stranger... thank the heavens. My family's heirloom — a red gem older than this village — has been stolen. A bandit has been camping to the south-west, drinking himself stupid on what he can rob from travelers. He took it three nights past while I slept. Please... I have not the strength left to fetch it myself.\"",
			"choices": [
				{"id":"accept", "text":"I'll find your gem. You have my word.",
					"actions":["set_flag:elder_briefed=true"], "next":"intro_accept"},
				{"id":"ask_pay", "text":"What's in it for me?", "next":"intro_payment"},
				{"id":"refuse", "text":"Find someone else.", "next":"intro_refuse"},
			],
		},
		"intro_payment": {
			"text": "\"I am not a wealthy man, but I have set aside a purse of gold for whoever returns my gem. Take it as recompense for the trouble — and ask not how an old man came by it.\"",
			"choices": [
				{"id":"accept_after_pay", "text":"Then I'll fetch it.",
					"actions":["set_flag:elder_briefed=true"], "next":"intro_accept"},
				{"id":"refuse_after_pay","text":"Not enough.", "next":"intro_refuse"},
			],
		},
		"intro_refuse": {
			"text": "\"Then go in peace. May you sleep more soundly than I do tonight.\"",
			"choices": [],
		},
		"intro_accept": {
			"text": "\"Bless you. The bandit's camp is to the south-west — you can't miss the smoke. Try... try not to start a fire if there is another way. He was a good man, once.\"",
			"choices": [],
		},
		"start_in_progress": {
			"text": "\"Back already? Without the gem? The bandit is to the SOUTH-WEST, friend. Mind the brambles.\"",
			"choices": [
				{"id":"reassure", "text":"I'll find it. I just needed a moment.", "next":"end"},
				{"id":"vent", "text":"That bandit is more trouble than he looks.", "next":"vent_reply"},
				# Only available if the bandit has shared his backstory with you.
				{"id":"confront", "text":"He says the gem belonged to his mother. Is that true?",
					"requires":{"flag:bandit_sympathy":"true"}, "next":"confront_response"},
			],
		},
		"confront_response": {
			"text": "The Elder is silent a long while. His mouth works without sound. \"...So he told you. I had hoped he'd forgotten. I won that gem from his mother in a fool's wager when she was sick and out of coin and could not refuse the table. I have carried that shame these forty years. It IS his by blood. But it is also all I have left of her — she was a friend to me, before. Whatever you do with this knowledge, do it kindly.\"",
			"choices": [
				{"id":"will_mediate", "text":"Then let me try to set this right between you.",
					"actions":["set_flag:elder_confessed=true"], "next":"mediate_blessing"},
				{"id":"will_take", "text":"You don't deserve it. I'll take it to him.",
					"actions":["set_flag:elder_confessed=true"], "next":"angry_dismiss"},
				{"id":"shrug", "text":"That's between you two. (leave)", "next":"end"},
			],
		},
		"mediate_blessing": {
			"text": "The Elder bows his head. \"Then you carry more than a gem. Tell him... tell him I'm sorry. I should have said it forty years ago.\"",
			"choices": [],
		},
		"angry_dismiss": {
			"text": "\"Fair. I'll not stop you.\" His eyes do not meet yours.",
			"choices": [],
		},
		"vent_reply": {
			"text": "\"Aye. He always was a slippery one, even as a boy. If words won't move him, perhaps a sharper tongue will.\"",
			"choices": [],
		},
		"start_has_gem": {
			"text": "The Elder's eyes widen. \"You have it. By the saints — you actually have it. Hand it here, hand it here, my hands are shaking...\"",
			"choices": [
				{"id":"hand_gem", "text":"(Hand over the gem.)", "next":"end"},
				{"id":"keep_it", "text":"Hmm... actually, this gem is rather pretty.", "next":"keep_response"},
			],
		},
		"keep_response": {
			"text": "\"You wouldn't. You promised. ...You promised.\"",
			"choices": [
				{"id":"return_it","text":"You're right. (Return to handing it over.)", "next":"start_has_gem"},
				{"id":"walk_away","text":"(walk away)", "next":"end"},
			],
		},
		"start_done": {
			"text": "\"My friend. Sit, sit. The gem is on its altar again, where it belongs. Whatever you did out there — I will not ask. Some debts are paid in silver, but yours is paid in something I cannot put a name to.\"",
			"choices": [],
		},
		"start_failed": {
			"text": "(There is no answer. The Elder is gone.)",
			"choices": [],
		},
	}
	# Choosing "hand_gem" doesn't itself transfer the item — the actual
	# transfer is the player picking the gem in the standard Give flow once
	# the conversation closes. To make handover happen IN the dialog, expose
	# a "Give" affordance: we add it as an action.
	elder.dialog_tree["start_has_gem"]["choices"][0]["actions"] = ["take_player:gem_red"]
	level_root.add_child(elder)

	# --- Bandit (south-west) — quest target with rich dialog tree ---
	var bandit := NPC.new()
	bandit.npc_name = "Bandit"
	bandit.character_sheet = "Hunter"
	bandit.role = "bandit"
	bandit.max_health = 4
	bandit.initial_items = [{"id":"gem_red","count":1}, {"id":"coin_gold","count":1}]
	bandit.position = Vector2(6 * TILE, (H - 8) * TILE)
	bandit.start_nodes = [
		{"node":"start_mediated",  "requires":{"flag:mediated":"true"}},
		{"node":"start_post_deal", "requires":{"flag:persuaded":"true"}},
		{"node":"start_post_deal", "requires":{"flag:bribed":"true"}},
		{"node":"start_post_food", "requires":{"flag:traded_food":"true"}},
		{"node":"start_post_intimidated", "requires":{"flag:intimidated":"true"}},
		{"node":"start_post_ally", "requires":{"flag:bandit_ally":"true"}},
		{"node":"start_briefed",   "requires":{"flag:elder_briefed":"true"}},
		{"node":"start_unbriefed", "requires":{}},
	]
	bandit.dialog_start = "start_unbriefed"
	bandit.dialog_tree = {
		"start_unbriefed": {
			"text": "A wiry man slouches against a half-burnt tree, knife in his lap. He doesn't bother standing. \"You're a long way from anywhere, friend. Either you're lost, or you're nosy, and either way it's a problem for one of us.\"",
			"choices": [
				{"id":"who_are_you", "text":"Who are you?", "next":"who_reply"},
				{"id":"leave_unbriefed", "text":"My mistake. (leave)", "next":"end"},
			],
		},
		"who_reply": {
			"text": "\"Names are for tax collectors. Folks around here just call me trouble. Now, was there something you wanted, or did you come to admire the view?\"",
			"choices": [
				{"id":"leave_uncurious", "text":"Just passing through.", "next":"end"},
			],
		},
		"start_briefed": {
			"text": "The Bandit recognises you. \"Ah. The old man finally got someone to do his fetching for him, did he? I wondered when this little drama would reach me. Get to the point — what's it going to be?\"",
			"choices": [
				{"id":"ask_gem", "text":"The red gem. I want it back.", "next":"ask"},
				{"id":"ally_offer", "text":"What if I weren't on his side?", "next":"ally"},
				{"id":"why_take", "text":"Why did you steal it in the first place?", "next":"backstory"},
				{"id":"leave_briefed", "text":"I've heard enough. (leave)", "next":"end"},
			],
		},
		"backstory": {
			"text": "He laughs, dry as dust. \"Steal? That gem belonged to my mother before that old crow ever set eyes on it. He won it off her in a card game when I was a boy and her hands were too tired to count. So no, I didn't steal it. I took it back.\"",
			"choices": [
				{"id":"believe", "text":"...That changes things.",
					"actions":["set_flag:bandit_sympathy=true"], "next":"backstory_after"},
				{"id":"disbelieve", "text":"Convenient story.", "next":"ask"},
			],
		},
		"backstory_after": {
			"text": "\"Good of you to listen. Doesn't change what you came for, though. Make your choice.\"",
			"choices": [
				{"id":"ask_gem2", "text":"I still need the gem.", "next":"ask"},
				{"id":"ally_offer2","text":"Maybe the old man's the one who should answer for this.", "next":"ally"},
			],
		},
		"ask": {
			"text": "\"So you want the red rock. Course you do. Well, I'm a reasonable sort, when the wind's right. Pick a wind.\"",
			"choices": [
				{"id":"persuade_honest", "text":"He's a frail old man. Just return it — call it a kindness.",
					"actions":["set_flag:persuaded=true","give_player:gem_red"], "next":"honest_out"},
				{"id":"persuade_bribe", "text":"I can pay you a coin for it.",
					"actions":["take_player:coin_gold","set_flag:bribed=true","give_player:gem_red"], "next":"bribe_out"},
				# Sword threat — only visible if the player has a sword equipped on hand.
				{"id":"threaten_sword", "text":"[draw blade] You can hand it over, or I can take it.",
					"requires":{"inv:sword":">=1"},
					"actions":["set_flag:intimidated=true","give_player:gem_red"], "next":"intimidated_out"},
				# Trade food — only when player carries food in their bag.
				{"id":"trade_fish", "text":"I have fish to spare. Trade?",
					"requires":{"inv:fish":">=1"},
					"actions":["take_player:fish","set_flag:traded_food=true","give_player:gem_red"], "next":"food_out"},
				{"id":"trade_meat", "text":"How about a hot meal? I have meat.",
					"requires":{"inv:meat":">=1"},
					"actions":["take_player:meat","set_flag:traded_food=true","give_player:gem_red"], "next":"food_out"},
				{"id":"trade_honey", "text":"Sweet tooth? I have honey.",
					"requires":{"inv:honey":">=1"},
					"actions":["take_player:honey","set_flag:traded_food=true","give_player:gem_red"], "next":"food_out"},
				# Mediation finisher — only available if both backstory and elder's confession are unlocked.
				{"id":"deliver_truth", "text":"The Elder confessed. He's sorry. He said he should have said so forty years ago.",
					"requires":{"flag:bandit_sympathy":"true","flag:elder_confessed":"true"},
					"actions":["set_flag:mediated=true","give_player:gem_red"], "next":"mediate_out"},
				{"id":"insult", "text":"Hand it over before I make you.", "next":"insult_out"},
				{"id":"back", "text":"(say nothing — step back)", "next":"start_briefed"},
			],
		},
		"intimidated_out": {
			"text": "He weighs his knife against your steel and decides he likes his hand the way it is. Spits, pulls the gem from his belt, and slings it at your feet. \"Take it. Walk away. Don't ever come back here.\"",
			"choices": [],
		},
		"food_out": {
			"text": "He blinks at the offering, then laughs — short and surprised. \"You've a strange way of bargaining.\" He eats. He chews. He hands you the gem. \"For the meal. Wasn't expecting kindness today.\"",
			"choices": [],
		},
		"mediate_out": {
			"text": "He stares at you. The smirk leaves his face for the first time. \"He said that? After all this time?\" He turns the gem over once, twice, then presses it into your hand. \"Take it back to him. Tell him... tell him I heard. And tell him my mother forgave him long before I was old enough to understand.\"",
			"choices": [],
		},
		"honest_out": {
			"text": "He stares at you a long moment, then snorts and tosses you the gem. \"Tell the old fool he doesn't deserve you. And tell him we're square.\"",
			"choices": [],
		},
		"bribe_out": {
			"text": "He bites the coin, grins yellow, and presses the gem into your palm. \"Pleasure doing business. The old man's a piece of work, but coin spends the same.\"",
			"choices": [],
		},
		"insult_out": {
			"text": "His grin goes flat. \"Then we'll see whose hands shake first.\" He doesn't give you the gem. (Draw your sword if you mean it.)",
			"choices": [],
		},
		"ally": {
			"text": "He tilts his head. \"Now THAT is interesting. You think the old crow has it coming, do you? Tell you what — you put him in the ground, and the gem's yours, plus a bit extra. He's got things in that hut of his I'd rather not chase down myself.\"",
			"choices": [
				{"id":"ally_accept", "text":"You have a deal.",
					"actions":["set_flag:bandit_ally=true"], "next":"ally_accepted"},
				{"id":"ally_decline", "text":"On reflection, no. (back)", "next":"start_briefed"},
			],
		},
		"ally_accepted": {
			"text": "\"Find me when it's done. Don't make me wait — patience and I parted ways years ago.\"",
			"choices": [],
		},
		"start_post_deal": {
			"text": "He nods at you with something almost like respect. \"Still breathing. Good. Go on — the old man's waiting.\"",
			"choices": [],
		},
		"start_post_ally": {
			"text": "\"Is it done? Don't make me ask twice.\"",
			"choices": [
				{"id":"not_yet","text":"Not yet.", "next":"end"},
			],
		},
		"start_post_food": {
			"text": "He raises a finger in mock salute. \"Decent traveler. Rare these days. Now leave me to my fire.\"",
			"choices": [],
		},
		"start_post_intimidated": {
			"text": "He doesn't look up. \"Move along.\"",
			"choices": [],
		},
		"start_mediated": {
			"text": "The bandit looks lighter than when you met him. \"Strange feeling, this. Forty years of cold smoke, and you blow it away in an afternoon. Go on, then. He's waiting for you.\"",
			"choices": [],
		},
	}
	level_root.add_child(bandit)
	level_root.add_child(_label_at(bandit.position + Vector2(0, -22), "Bandit"))

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
	camera = Camera2D.new()
	camera.zoom = Vector2(2, 2)
	camera.position_smoothing_enabled = true
	camera.position_smoothing_speed = 8.0
	player.add_child(camera)
	camera.make_current()

func _setup_hud() -> void:
	hud = Hud.new()
	add_child(hud)
	hud.bind_player(player)
	hud.toast("WASD move · J/Space attack · E interact · Q drop · 1-9 select", 4.0)

func _setup_quest_log() -> void:
	QuestManager.bind_player(player)
	quest_log = QuestLog.new()
	add_child(quest_log)

func _seed_sample_quests() -> void:
	# Single branching test quest with FOUR success paths and a fail
	# condition. Every branch and the fail are pure data — exactly the shape
	# the LLM phase will emit via add_quest_from_dict().
	QuestManager.add_quest_from_dict({
		"id": "stolen_heirloom",
		"title": "The Stolen Heirloom",
		"description": "The Elder's red gem was taken by a Bandit camped to the south-west. How you handle it is up to you.",
		"sequential": false,
		# No primary objectives — every path is a branch.
		"objectives": [],
		"rewards": [],
		"branches": [
			{
				"id": "combat",
				"description": "Kill the Bandit and return the gem.",
				"objectives": [
					{"type":"kill_npc","params":{"npc_name":"Bandit"},"required":1,"description":"Defeat the Bandit"},
					{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1,"description":"Give the gem to the Elder"},
				],
				"rewards": [{"item_id":"coin_gold","count":5},{"item_id":"potion_red","count":2}],
			},
			{
				"id": "persuade",
				"description": "Convince the Bandit to give the gem freely.",
				"requires_flags": {"persuaded":"true"},
				"objectives": [
					{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1,"description":"Return the gem to the Elder"},
				],
				"rewards": [{"item_id":"coin_gold","count":5},{"item_id":"key_silver","count":1},{"item_id":"potion_red","count":2}],
			},
			{
				"id": "bribe",
				"description": "Pay the Bandit off and return the gem.",
				"requires_flags": {"bribed":"true"},
				"objectives": [
					{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1,"description":"Return the gem to the Elder"},
				],
				"rewards": [{"item_id":"coin_gold","count":3},{"item_id":"key_silver","count":1}],
			},
			{
				"id": "side_with_bandit",
				"description": "Side with the Bandit. Eliminate the Elder.",
				"requires_flags": {"bandit_ally":"true"},
				"objectives": [
					{"type":"kill_npc","params":{"npc_name":"Elder"},"required":1,"description":"Eliminate the Elder"},
				],
				"rewards": [{"item_id":"axe","count":1},{"item_id":"gem_red","count":2},{"item_id":"coin_silver","count":3}],
			},
			{
				"id": "trade_food",
				"description": "Trade food to the Bandit and return the gem.",
				"requires_flags": {"traded_food":"true"},
				"objectives": [
					{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1,"description":"Return the gem to the Elder"},
				],
				"rewards": [{"item_id":"coin_gold","count":4},{"item_id":"key_silver","count":1},{"item_id":"meat","count":2}],
			},
			{
				"id": "intimidate",
				"description": "Threaten the Bandit at swordpoint and return the gem.",
				"requires_flags": {"intimidated":"true"},
				"objectives": [
					{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1,"description":"Return the gem to the Elder"},
				],
				"rewards": [{"item_id":"coin_gold","count":4}],
			},
			{
				"id": "mediate",
				"description": "Reconcile the Elder and the Bandit. Return the gem with the truth.",
				"requires_flags": {"mediated":"true"},
				"objectives": [
					{"type":"give","params":{"npc_name":"Elder","item_id":"gem_red"},"required":1,"description":"Return the gem to the Elder"},
				],
				"rewards": [{"item_id":"coin_gold","count":8},{"item_id":"key_gold","count":1},{"item_id":"medipack","count":1},{"item_id":"potion_red","count":2}],
			},
		],
		# If the Elder dies WITHOUT siding with the Bandit, the quest fails.
		# Branches are evaluated before fail conditions so side_with_bandit
		# wins when its flag is set.
		"fail_conditions": [
			{"type":"kill_npc","params":{"npc_name":"Elder"},"required":1,"description":"Killed the Elder"},
		],
	})

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
	if _current_npc == null: return
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
	dialog.show_node(npc.npc_name, node, visible)

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
	if nxt == null or String(nxt) == "" or String(nxt) == "end":
		dialog.close_dialog()
	else:
		_open_dialog_node(String(nxt))

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
				npc._die()

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
