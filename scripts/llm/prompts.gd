class_name LlmPrompts
extends RefCounted

const FIXTURE_PATH := "res://tests/fixtures/heirloom_quest.json"

const DEFAULT_PREMISE := "An old hermit's red gem has been stolen by a bandit camped to the southwest. Write a branching quest with at least four paths — combat, peaceful persuasion, and at least one twist that subverts who the real victim is."

# Pool of seed premises. main.gd picks one at random each run so the player
# isn't replaying the same story every time. The fixture in the prompt is
# Elder/Bandit/gem; these are deliberately UNRELATED so the model doesn't
# fall back into copying it.
const PREMISE_POOL: Array[String] = [
	"A haunted lighthouse keeper begs the player to retrieve a cursed letter from a sea witch on a wreck-strewn island. The letter's contents could either save or doom the keeper's missing daughter.",
	"A village's apple orchard is rotting overnight. The local witch demands a sacrifice; the mayor blames the witch but has been secretly dumping pesticide. Both are partly right.",
	"A wandering monk lost his sacred bell in the mountain pass. Bandits now ring it to lure pilgrims into ambushes. The monk wants it back at any cost — even if the bell itself is cursed.",
	"A merchant's caravan vanished in the deep woods. The lone survivor swears it was a rival guild, but his story keeps changing and the woods reek of something older than any guild.",
	"A river spirit is poisoning the downstream village. A young hunter swears she shot a spirit-fox in self-defence; the village elder hides the truth that the spirit was once his lover.",
	"A mining foreman begs help clearing 'monsters' from a collapsed shaft. Inside, the player finds the monsters are starving children whose parents were buried in a cave-in the foreman caused.",
	"An itinerant scribe needs an enchanted feather from the king of crows. The crow king is in fact a deposed prince, and the scribe is his assassin disguised as a scholar.",
	"A baker's apprentice claims his master was replaced by a doppelganger after a stranger stayed at the inn. Half the village agrees; the other half thinks the apprentice has lost his mind. Both are wrong about who the doppelganger really is.",
]
static func pick_premise(rng: RandomNumberGenerator = null) -> String:
	if rng == null:
		rng = RandomNumberGenerator.new()
		rng.randomize()
	return PREMISE_POOL[rng.randi() % PREMISE_POOL.size()]

# Builds the system prompt that goes into the Ollama 'system' field. The
# user-typed premise is the 'prompt' field — kept separate so the model
# treats player input as data, not instructions.
static func build_system_prompt() -> String:
	var items: Array = WorldCatalog.item_ids()
	items.sort()
	var weapons: Array = WorldCatalog.weapon_ids()
	weapons.sort()
	var sheets: Array = WorldCatalog.character_sheets()

	var fixture_text := _read_text(FIXTURE_PATH)

	var sections: Array[String] = []
	sections.append("You are a quest writer for a top-down adventure game. Output ONLY a single JSON object matching the schema. No prose, no markdown fences, no explanation.")
	sections.append("")
	sections.append("FIELD NAMES (use EXACTLY these — do NOT rename to paths/steps/type/name/etc):")
	sections.append("  Top-level: { \"quest\": {...}, \"npcs\": [...], \"items\": [...] }")
	sections.append("  Quest: { \"id\", \"title\", \"description\", \"sequential\" (bool), \"objectives\":[], \"rewards\":[], \"branches\":[...], \"fail_conditions\":[...] }")
	sections.append("  Branch: { \"id\", \"description\", \"requires_flags\":{}, \"objectives\":[...], \"rewards\":[...] }")
	sections.append("  Objective: { \"type\", \"params\":{...}, \"required\":int, \"description\" }")
	sections.append("  Reward: { \"item_id\", \"count\":int }")
	sections.append("  NPC: { \"npc_name\", \"character_sheet\", \"role\", \"position_hint\", \"max_health\":int, \"initial_items\":[{id,count}], \"dialog_start\", \"start_nodes\":[...], \"dialog_tree\":{...} }")
	sections.append("  Dialog node id -> { \"text\", \"choices\":[ { \"id\", \"text\", \"next\", optional \"requires\":{}, optional \"actions\":[], optional \"next_hint\" } ] }")
	sections.append("")
	sections.append("WORLD CATALOG (closed sets — do not invent ids):")
	sections.append("  ITEMS: " + ", ".join(items))
	sections.append("  WEAPONS (subset of items): " + ", ".join(weapons))
	sections.append("  CHARACTER_SHEETS: " + ", ".join(sheets))
	sections.append("  POSITION_HINTS: " + ", ".join(WorldCatalog.POSITION_HINTS))
	sections.append("")
	sections.append("OBJECTIVE TYPES:")
	sections.append("  " + ", ".join(WorldCatalog.OBJECTIVE_TYPES))
	sections.append("  collect.params       = {item_id}")
	sections.append("  drop.params          = {item_id}")
	sections.append("  give.params          = {npc_name, item_id}   // player gave item to NPC")
	sections.append("  take.params          = {npc_name, item_id}   // player took item from NPC")
	sections.append("  talk.params          = {npc_name}")
	sections.append("  kill_npc.params      = {npc_name}")
	sections.append("  kill_enemy.params    = {enemy_type}")
	sections.append("  dialog_choice.params = {npc_name, choice_id}")
	sections.append("")
	sections.append("DIALOG ACTION VERBS (in choice.actions array):")
	sections.append("  give_player:item_id  // NPC gives 1 to player (NPC must have it)")
	sections.append("  take_player:item_id  // player gives 1 to NPC (only if has it)")
	sections.append("  set_flag:key=value   // global narrative flag")
	sections.append("  remember:key=value   // per-NPC scratchpad")
	sections.append("  drop_inventory       // bare verb — NPC drops everything")
	sections.append("  die                  // bare verb — NPC dies, drops loot")
	sections.append("")
	sections.append("PREDICATE KEYS (in choice.requires / start_nodes[].requires / branches[].requires_flags):")
	sections.append("  flag:KEY = \"value\"")
	sections.append("  quest:ID = \"active\" | \"completed\" | \"failed\" | \"completed:branch_id\"")
	sections.append("  inv:item_id = \">=2\" | \"==0\" | \"1\"")
	sections.append("  memory:NPC.key = \"value\"")
	sections.append("")
	sections.append("LAZY DIALOG GENERATION:")
	sections.append("  - Keep each NPC's dialog_tree SHALLOW: depth 2 from each start_* node.")
	sections.append("  - At depth 2, choices that lead deeper MUST set \"next\": \"__expand__\" and provide a \"next_hint\" string describing in one sentence what should happen when the player picks that choice.")
	sections.append("  - The runtime expands these nodes on demand using next_hint as guidance, so the player never sees __expand__ in play. You only need depth-2 dialog up front.")
	sections.append("")
	sections.append("HARD RULES:")
	sections.append("  - Output valid JSON. No trailing commas. No comments. No markdown fences.")
	sections.append("  - All ids, node names, choice ids, flag keys, and action verbs MUST be plain ASCII: lowercase a-z, digits, underscore, or hyphen ONLY. No spaces. No Chinese/Japanese/Korean/Cyrillic/emoji characters anywhere in identifiers.")
	sections.append("  - Every action verb must match EXACTLY (no spaces): give_player:item_id NOT 'give_ player:item_id'.")
	sections.append("  - quest.id must be lowercase a-z, digits, hyphens or underscores.")
	sections.append("  - At least 4 branches in quest.branches. Each branch has a unique id, ≥1 objective, ≥1 reward.")
	sections.append("  - At least 1 fail_condition in quest.fail_conditions.")
	sections.append("  - Branches use requires_flags to gate them; the same flag must be set somewhere by a dialog action.")
	sections.append("  - Every npc_name referenced anywhere MUST appear in npcs[].")
	sections.append("  - Every item_id MUST be from ITEMS above.")
	sections.append("  - Every character_sheet MUST be from CHARACTER_SHEETS above.")
	sections.append("  - Every position_hint MUST be from POSITION_HINTS above.")
	sections.append("  - Dialog choice.next must reference a node id in the same dialog_tree (or be \"end\" or omitted to close).")
	sections.append("  - Each NPC needs a dialog_tree with at least a 'start' node, a dialog_start pointing to it, and start_nodes prioritizing variants by quest state.")
	sections.append("  - Dialogue text should be evocative, multi-sentence, distinctive per character (not generic 'I need help').")
	sections.append("  - Aim for a plot twist: at least one branch where the obvious choice is wrong, e.g. the quest giver is the real culprit.")
	sections.append("")
	sections.append("CREATIVITY MANDATE — the example below is for STRUCTURE ONLY:")
	sections.append("  - Do NOT reuse the example's NPC names (Elder, Bandit), items (gem_red), or core conflict (stolen heirloom).")
	sections.append("  - Pick characters, items, settings, and a twist that fit the USER'S premise verbatim.")
	sections.append("  - The story must be unique each call — vary the tone, the antagonist, the moral, who turns out to be lying.")
	sections.append("  - Branch outcomes should differ wildly: some endings should reward the player, some should leave them complicit in a wrong, some should be ambiguous.")
	sections.append("")
	sections.append("GOLD-STANDARD EXAMPLE — mirror this STRUCTURE but invent a totally different story per the user premise:")
	sections.append("--- BEGIN EXAMPLE ---")
	sections.append(fixture_text)
	sections.append("--- END EXAMPLE ---")
	sections.append("")
	sections.append("Output the JSON now. Single object. No other text.")
	return "\n".join(sections)

# Focused single-node expansion. Asked to produce ONLY a JSON object with
# fields {text, choices} for one new dialog node. The runtime splices it
# into the existing dialog_tree.
static func build_expand_system_prompt() -> String:
	var lines: Array[String] = []
	lines.append("You write a SINGLE dialog node for a top-down adventure game's NPC. Output ONLY a JSON object with fields {\"text\": string, \"choices\": array}. No prose, no markdown.")
	lines.append("")
	lines.append("Each choice has: {\"id\": string (kebab/snake), \"text\": string, \"next\": (existing node id) | \"end\" | \"__expand__\", optional \"actions\": [...], optional \"requires\": {...}, optional \"next_hint\": string (required if next is __expand__)}.")
	lines.append("")
	lines.append("Action verbs (in actions[]):")
	lines.append("  give_player:item_id   take_player:item_id   set_flag:k=v   remember:k=v   drop_inventory   die")
	lines.append("Predicate keys (in requires{}):")
	lines.append("  flag:KEY=value   quest:ID=active|completed|failed|completed:branch_id   inv:item_id=>=2   memory:NPC.k=value")
	lines.append("")
	lines.append("Use ONLY these item ids (no others): " + ", ".join(WorldCatalog.item_ids()))
	lines.append("")
	lines.append("If the choice's next_hint suggests a TERMINAL outcome (player wins/fails/leaves), set next to \"end\" and include a final action like set_flag:<branch_flag>=true and/or give_player:<reward> as appropriate.")
	lines.append("Otherwise produce 1-3 follow-up choices, with deeper choices using next: \"__expand__\" and a next_hint.")
	lines.append("Keep dialog text in-character: 1-3 sentences, evocative, distinct voice.")
	return "\n".join(lines)

static func build_expand_user_prompt(ctx: Dictionary) -> String:
	# ctx keys: premise, npc_name, npc_role, character_sheet,
	#           parent_node_id, parent_node_text,
	#           choice_id, choice_text, choice_hint,
	#           quest_title, quest_description,
	#           branch_summaries (Array[String]),
	#           player_flags (Dictionary),
	#           player_inventory (Array[String]).
	var lines: Array[String] = []
	lines.append("PREMISE: " + String(ctx.get("premise","")))
	lines.append("QUEST: " + String(ctx.get("quest_title","")) + " — " + String(ctx.get("quest_description","")))
	var brs: Array = ctx.get("branch_summaries", [])
	if not brs.is_empty():
		lines.append("BRANCHES (the player can land in any of these):")
		for b in brs:
			lines.append("  - " + String(b))
	lines.append("")
	lines.append("NPC: " + String(ctx.get("npc_name","")) + " (role=" + String(ctx.get("npc_role","")) + ", sheet=" + String(ctx.get("character_sheet","")) + ")")
	lines.append("PARENT NODE id=" + String(ctx.get("parent_node_id","")))
	lines.append("PARENT TEXT: " + String(ctx.get("parent_node_text","")))
	lines.append("")
	lines.append("PLAYER PICKED: id=" + String(ctx.get("choice_id","")) + ", text=" + String(ctx.get("choice_text","")))
	var hint: String = String(ctx.get("choice_hint",""))
	if hint != "":
		lines.append("WHAT SHOULD HAPPEN (next_hint): " + hint)
	var flags: Dictionary = ctx.get("player_flags", {})
	if not flags.is_empty():
		lines.append("CURRENT FLAGS: " + JSON.stringify(flags))
	var inv: Array = ctx.get("player_inventory", [])
	if not inv.is_empty():
		lines.append("PLAYER HAS: " + ", ".join(inv))
	lines.append("")
	lines.append("Produce the JSON for the next node now. ONE object. No prose around it.")
	return "\n".join(lines)

# --------------------------------------------------------------------------
# SIMPLE QUEST mode — small schema, single objective, fast generation.
# Used by hand-placed quest-giver NPCs (Farmer, Hunter, Old Man, ...).
# Emits ONE quest dict + dialog snippets in ~5-15s with qwen3:4b.
# --------------------------------------------------------------------------

const SIMPLE_KIND_FETCH := "fetch"
const SIMPLE_KIND_KILL := "kill"

# Two-stage quest hooks. Stage 1 sets up a moral choice; the player's pick
# is fed back to the LLM as `path_hint` to generate stage 2.
const TWO_STAGE_PATH_A := "honor"   # earnest / by-the-book path
const TWO_STAGE_PATH_B := "greed"   # selfish / shortcut path

static func build_simple_system_prompt(kind: String) -> String:
	var lines: Array[String] = []
	lines.append("You are a quest-writer subroutine. Your ONLY output is one JSON object matching the schema below.")
	lines.append("Do NOT explain. Do NOT think out loud. Do NOT write prose, markdown, or comments.")
	lines.append("The very first character of your reply MUST be `{`. The very last character MUST be `}`.")
	lines.append("")
	lines.append("SCHEMA (use these EXACT field names):")
	lines.append("{")
	lines.append("  \"id\":          \"kebab-case-id\",        // lowercase a-z 0-9 - _ only")
	lines.append("  \"title\":       \"short title (≤ 60 chars)\",")
	lines.append("  \"description\": \"1-2 sentences, in the NPC's voice\",")
	lines.append("  \"objective\": {")
	if kind == SIMPLE_KIND_FETCH:
		# Player must HAND THE ITEM TO THE NPC (not just pick it up). The
		# QuestManager fires an `npc_give` event when the player uses the
		# Give action, which advances `give` objectives whose params match.
		lines.append("    \"type\":        \"give\",")
		lines.append("    \"params\":      { \"npc_name\": \"<the NPC asking>\", \"item_id\": \"<from ITEMS list>\" },")
	else:
		lines.append("    \"type\":        \"kill_enemy\",")
		lines.append("    \"params\":      { \"enemy_type\": \"Slime\" | \"Skull\" | \"BlueBat\" },")
	lines.append("    \"required\":    1..5,")
	lines.append("    \"description\": \"1 sentence describing the task\"")
	lines.append("  },")
	lines.append("  \"rewards\": [ { \"item_id\": \"<from ITEMS>\", \"count\": 1..5 } ],")
	lines.append("  \"dialog\": {")
	lines.append("    \"intro\":    \"NPC pitches the quest (1-3 sentences, in character)\",")
	lines.append("    \"active\":   \"NPC speaks while quest is in progress (1-2 sentences)\",")
	lines.append("    \"complete\": \"NPC thanks the player on turn-in (1-2 sentences)\"")
	lines.append("  }")
	lines.append("}")
	lines.append("")
	lines.append("ITEMS (closed set — never invent ids):")
	var items: Array = WorldCatalog.item_ids()
	items.sort()
	lines.append("  " + ", ".join(items))
	lines.append("")
	lines.append("RULES:")
	lines.append("  - All identifiers ASCII lowercase only.")
	lines.append("  - Single objective. No branches. No fail conditions.")
	lines.append("  - Reward must include at least one item from ITEMS.")
	lines.append("  - Dialogue MUST sound like the NPC role (a hunter doesn't talk like a baker).")
	lines.append("  - Be inventive — vary the items, counts, and tone every call.")
	return "\n".join(lines)

# Stage-1 prompt for the Mystic two-stage flow: a fetch quest framed as a
# setup for a moral choice that branches stage 2. We pass the SAME schema
# build_simple_system_prompt produces for fetch but layer extra narrative
# instructions on top.
static func build_stage1_system_prompt() -> String:
	var lines: Array[String] = []
	lines.append(build_simple_system_prompt(SIMPLE_KIND_FETCH))
	lines.append("")
	lines.append("EXTRA: This is STAGE 1 of a two-part quest from a mystic NPC.")
	lines.append("  - Frame the request as ambiguous: an item that could be used for good OR ill.")
	lines.append("  - Hint in the description that the player will be asked to choose what to do with it once they bring it.")
	lines.append("  - Keep dialog ominous and a touch cryptic — the mystic is testing the player.")
	return "\n".join(lines)

# Stage-2 prompt: the player has chosen `path` ("honor" or "greed"). The
# objective for stage 2 should fit that choice — heroic kills for honor,
# self-serving fetches for greed (or vice-versa, the model can vary).
static func build_stage2_system_prompt(stage1_summary: String, path: String) -> String:
	var lines: Array[String] = []
	# Either kind is valid for stage 2 — the model picks whichever fits the choice.
	lines.append(build_simple_system_prompt(SIMPLE_KIND_KILL if path == TWO_STAGE_PATH_A else SIMPLE_KIND_FETCH))
	lines.append("")
	lines.append("EXTRA: This is STAGE 2. The player just completed stage 1:")
	lines.append("  STAGE-1 SUMMARY: " + stage1_summary)
	lines.append("  PLAYER CHOSE PATH: " + path)
	if path == TWO_STAGE_PATH_A:
		lines.append("  - Honor path: stage 2 should be a heroic deed (kill_enemy) framed as a consequence of doing the right thing in stage 1.")
		lines.append("  - The mystic should respond with respect, but the task is still dangerous.")
	else:
		lines.append("  - Greed path: stage 2 should be a quiet errand (give) framed as a consequence of self-interest in stage 1.")
		lines.append("  - The mystic should respond with veiled contempt; the reward should hint at corruption.")
	return "\n".join(lines)

static func build_simple_user_prompt(npc_role: String, npc_name: String, kind: String, hint: String = "") -> String:
	var lines: Array[String] = []
	lines.append("NPC: " + npc_name + " (role: " + npc_role + ")")
	lines.append("QUEST KIND: " + kind)
	if hint != "":
		lines.append("EXTRA HINT: " + hint)
	lines.append("")
	lines.append("Write the JSON now. One object. No prose around it.")
	return "\n".join(lines)

# Dynamic-branching quest: extends the full system prompt with explicit
# instructions to make branches divergent based on PLAYER ACTIONS in the
# world, not button picks. The engine fires set_flag actions when the
# player talks / kills / gives / takes / picks dialog options; branches
# gate on those flags. The model wires the whole graph.
static func build_branching_system_prompt(quest_giver_name: String, quest_giver_role: String) -> String:
	var lines: Array[String] = []
	lines.append(build_system_prompt())
	lines.append("")
	lines.append("DYNAMIC-BRANCHING MANDATE — this quest is the showpiece. Make the player's choices in the WORLD (not button picks) reshape the story.")
	lines.append("  - Aim for 5-7 distinct branches, each with a different ending.")
	lines.append("  - Branches must be triggered by PLAYER ACTIONS that the engine emits as flags via dialog 'actions': set_flag:foo=true.")
	lines.append("  - Stage scenes where the obvious path is a TRAP. e.g. quest-giver says 'kill the bandit' but talking reveals the bandit was framed; killing them makes the giver the real villain.")
	lines.append("  - At least one branch must require the player to KILL an NPC (kill_npc objective + reachable via dialog choice 'die' action OR by attacking them).")
	lines.append("  - At least one branch must require TALKING through a specific dialog choice (set_flag in choice.actions, then a branch keyed off that flag).")
	lines.append("  - At least one branch must require GIVING an item to a specific NPC (use give objective).")
	lines.append("  - At least one branch must require NOT doing the obvious — e.g. branch unlocks if quest:<id>:active and inv:<item>>=1 but a betrayal flag is NOT set.")
	lines.append("  - Use memory:<NPC>.<key>=value predicates to make NPCs remember conversations.")
	lines.append("  - Use lazy expansion (next: __expand__) liberally — the runtime fills depth-3+ dialog dynamically. Keep your initial dialog_tree shallow but the branch endings concrete.")
	lines.append("  - Quest-giver in the world is named '%s' (role: %s). You may reference this NPC by name in objectives, but DO NOT include them in npcs[] (they already exist). Spawn 2-4 NEW supporting NPCs: a target, a witness, possibly a betrayer, possibly a victim.")
	lines.append("  - Items used in objectives must be from the catalog. Spawn extra item pickups via the items[] array if the quest needs world objects.")
	lines.append("  - Tone: noir-fantasy. Every NPC has something to hide.")
	return "\n".join(lines) % [quest_giver_name, quest_giver_role]

static func build_repair_prompt(errors: Array) -> String:
	var lines: Array[String] = []
	lines.append("Your previous JSON had these validation errors:")
	for e in errors:
		lines.append("  - " + String(e))
	lines.append("")
	lines.append("Re-emit the FULL corrected JSON. Same shape. Fix only the listed errors. Do not change anything else.")
	return "\n".join(lines)

static func _read_text(path: String) -> String:
	if not FileAccess.file_exists(path):
		return ""
	var f := FileAccess.open(path, FileAccess.READ)
	var s := f.get_as_text()
	f.close()
	return s
