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
static func build_system_prompt(include_fixture: bool = true) -> String:
	var items: Array = WorldCatalog.item_ids()
	items.sort()
	var weapons: Array = WorldCatalog.weapon_ids()
	weapons.sort()
	var sheets: Array = WorldCatalog.character_sheets()

	# The gold-standard heirloom fixture is ~3K tokens. Skip it for
	# callers (the branching path) that already include their own
	# concrete examples and would otherwise blow Groq's per-request TPM.
	var fixture_text := _read_text(FIXTURE_PATH) if include_fixture else ""

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
	if include_fixture and fixture_text != "":
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
	# CRITICAL constraints surface FIRST so the model treats them as the
	# primary frame, not afterthoughts. LLMs typically over-weight the
	# top of system prompts.
	lines.append("=== CRITICAL WORLD CONSTRAINTS — read first, obey above all else ===")
	lines.append("This is a SINGLE-VILLAGE map with stationary NPCs. The player can:")
	lines.append("  • walk to NPCs, • pick dialog choices, • give/take items, • attack/kill NPCs.")
	lines.append("There is NO travel, NO time-of-day, NO 'investigate location', NO escort/follow.")
	lines.append("If a dialog choice or NPC line implies any of those mechanics, IT IS WRONG.")
	lines.append("Replace location pointers with 'Talk to <NPC>' or 'Bring <item> to <NPC>'.")
	lines.append("")
	# Skip the heirloom fixture — its ~3K tokens push the request past
	# Groq's per-minute TPM cap. The branching mandate below has its own
	# explicit examples so the model still has structure to mirror.
	lines.append(build_system_prompt(false))
	lines.append("")
	lines.append("=== DYNAMIC-BRANCHING MANDATE ===")
	lines.append("This quest is the showpiece. Player choices in the WORLD (not button picks) reshape the story.")
	lines.append("  - 5-7 distinct branches, each with a clearly different ending.")
	lines.append("  - Branches gate on flags that engine fires when the player acts: set_flag:foo=true in choice.actions, kill_npc events, give events, etc.")
	lines.append("  - Stage scenes where the obvious path is a TRAP (e.g. giver says 'kill the bandit' but talking first reveals the bandit was framed).")
	lines.append("  - REQUIRED branches:")
	lines.append("      1. KILL branch: kill_npc objective on a specific spawned NPC.")
	lines.append("      2. TALK branch: dialog_choice objective on a spoken choice that set_flags.")
	lines.append("      3. GIVE branch: give objective handing an item to a spawned NPC.")
	lines.append("      4. SUBTLE branch: gated by NOT doing the obvious — requires_flags has a key set to 'false' or omits a flag the other branches set.")
	lines.append("  - NPCs use memory:<NpcName>.<field>=value predicates to remember things across conversations.")
	lines.append("  - Tone: noir-fantasy. Every NPC has something to hide.")
	lines.append("")
	lines.append("=== CRITICAL SCHEMA RULES (do NOT violate; rejections will retry and burn your output) ===")
	lines.append("OBJECTIVE TYPES — these are the ONLY values for `objective.type`:")
	lines.append("  collect, drop, give, take, talk, kill_enemy, kill_npc, dialog_choice, reach")
	lines.append("  DO NOT use 'flag' or 'meet' or 'investigate' or any invented type.")
	lines.append("")
	lines.append("ACTION VERBS (in dialog choice.actions array) — strict closed set:")
	lines.append("  give_player:item_id    NPC gives item to player")
	lines.append("  take_player:item_id    player gives item to NPC")
	lines.append("  set_flag:key=value     set a global narrative flag")
	lines.append("  remember:key=value     set a per-NPC scratchpad value")
	lines.append("  drop_inventory         (bare) NPC drops everything")
	lines.append("  die                    (bare) NPC dies and drops loot. ⚠ DANGEROUS:")
	lines.append("                         the NPC is REMOVED from the world. Use ONLY when this NPC is supposed to be eliminated as a final narrative beat.")
	lines.append("                         Do NOT put 'die' on choices that are part of an ongoing conversation. Never put 'die' on an NPC who is the target of any give/take/talk/dialog_choice objective.")
	lines.append("  WRONG examples we keep seeing — DO NOT emit these:")
	lines.append("    memory:k=v          ← wrong; 'memory:' is a PREDICATE prefix, not an action. Use remember:k=v")
	lines.append("    kill_npc:Bob        ← wrong; kill_npc is an OBJECTIVE TYPE. To make an NPC die from dialog, use the bare verb 'die'.")
	lines.append("    quest:foo=active    ← wrong; 'quest:' is a PREDICATE prefix. Set quest progress with set_flag.")
	lines.append("")
	lines.append("PREDICATE KEYS (in choice.requires / start_nodes[].requires / branches[].requires_flags):")
	lines.append("  flag:KEY = \"value\"")
	lines.append("  quest:ID = \"active\" | \"completed\" | \"failed\" | \"completed:branch_id\"")
	lines.append("  inv:item_id = \">=2\" | \"==0\" | \"1\"")
	lines.append("  memory:NPCNAME.fieldname = \"value\"   ← NOTE the DOT between NPC and field, not a colon")
	lines.append("  WRONG: memory:NPCNAME:fieldname  ← the part after 'memory:' must use DOT")
	lines.append("")
	lines.append("WORLD CONSTRAINTS — what the player can actually do:")
	lines.append("  - Walk around a single small village. THAT IS THE ENTIRE WORLD.")
	lines.append("  - Talk to NPCs (only the ones in npcs[]), pick dialog choices, give/take items, attack and kill NPCs/enemies.")
	lines.append("")
	lines.append("FORBIDDEN — never reference these in dialog TEXT or in choices:")
	lines.append("  - Any LOCATION other than 'here' / 'the village' / 'the square' / vague 'nearby'.")
	lines.append("    NO 'mine', 'windmill', 'inn', 'tavern', 'cliff', 'forest', 'old tower', 'cave', 'shrine',")
	lines.append("    'bridge', 'docks', 'graveyard', 'crossroads', 'caravan camp', 'lighthouse', etc.")
	lines.append("  - Any TIME-of-day — no 'midnight', 'dawn', 'tonight', 'tomorrow', 'before sunset'.")
	lines.append("  - Any TRAVEL or RENDEZVOUS — no 'meet me at...', no 'follow the X', no 'go to Y'.")
	lines.append("  - Cryptic clues that point at unimplementable mechanics ('follow the heart-shaped stone').")
	lines.append("  - Asking an NPC to FOLLOW or ACCOMPANY or WALK-WITH the player. NPCs cannot move. Choices like")
	lines.append("    'Ask X to come with you' / 'Lead me to Y' / 'Take me to him' are FORBIDDEN. NPCs stay rooted")
	lines.append("    where they spawned. The player walks to NPCs, not the other way around.")
	lines.append("  - Choices that would 'lead the player' anywhere — there's nowhere to be led.")
	lines.append("")
	lines.append("REPLACE LOCATION HOOKS WITH NPC HOOKS:")
	lines.append("  ❌ 'Find me at the old mine.'")
	lines.append("  ✅ 'Talk to the Wanderer — he knows what to do next.'")
	lines.append("  ❌ 'Meet me at midnight.'")
	lines.append("  ✅ 'Bring back the gem and the Wanderer will explain.'")
	lines.append("  Every story beat resolves through TALKING to a named NPC, GIVING / TAKING an item, or KILLING — nothing else.")
	lines.append("")
	lines.append("  - Every dialog choice or NPC instruction MUST be achievable via the existing actions/objectives.")
	lines.append("  - When an NPC sets a task ('prove yourself'), the SAME node MUST also include a concrete way to do it as another choice OR the NPC's dialog should immediately reveal that task in the current node's options.")
	lines.append("")
	lines.append("BRANCH RULES:")
	lines.append("  - Every branch MUST have ≥2 objectives AND ≥1 reward. A single-objective branch (e.g. 'talk to witness, done') resolves the quest in one click and feels anticlimactic.")
	lines.append("  - Pair each branch's setup objective (talk / kill / collect) with a CONCLUSION objective: report back to the quest-giver via talk:<giver_name>, OR give a meaningful item to them, OR meet a final dialog_choice.")
	lines.append("  - Every objective references a real npc_name (from npcs[] or the existing quest-giver) and a real item_id (from ITEMS catalog).")
	lines.append("  - DO NOT invent items. If you need a 'magic locket', pick from: gem_red, gem_green, key_gold, book, letter, feather, etc.")
	lines.append("")
	lines.append("=== WORLD CONTEXT ===")
	lines.append("Quest-giver: '%s' (role: %s) — already exists in the world.")
	lines.append("  - You MAY reference '%s' by name in objectives (give/talk/kill_npc).")
	lines.append("  - You MUST NOT include '%s' in npcs[]. The npcs[] array is for NEW NPCs the quest spawns.")
	lines.append("  - Spawn 2-4 NEW supporting NPCs for the quest (target, witness, betrayer, victim).")
	lines.append("")
	lines.append("LAZY DIALOG: deeper choices may use next: \"__expand__\" + a next_hint string. Keep dialog_tree depth ≤ 2 from each start_* node.")
	lines.append("")
	lines.append("=== FINAL REMINDER (do not skip) ===")
	lines.append("Before emitting JSON, scan every choice.text and node.text. If any contains:")
	lines.append("  windmill / mine / inn / cave / forest / cliff / shrine / tower / bridge / docks / midnight / tonight / 'investigate <place>' / 'follow <X>' / 'meet <X> at <Y>' / 'lead/take me to' / 'come with me'")
	lines.append("→ rewrite that choice to use ONLY 'Talk to <NPC>', 'Give <item> to <NPC>', 'Take <item>', or 'Confront/Attack <NPC>'.")
	lines.append("EVERY action a player can take resolves through: TALK / GIVE / TAKE / KILL on a named NPC. Nothing else exists.")
	lines.append("")
	lines.append("=== STATE-AWARE NPC DIALOG (REQUIRED) ===")
	lines.append("Every spawned NPC MUST have AT LEAST 2 start_nodes so re-visiting them doesn't replay the intro:")
	lines.append("  1. The first-meet node (default).")
	lines.append("  2. A 'post-meet' node gated on a `met_<npc_id>` flag. Greets the player as already-known.")
	lines.append("  3. (Optional) A 'quest-progress' node gated on a flag set by the player's earlier choice.")
	lines.append("")
	lines.append("In the FIRST node's choices, ALWAYS include set_flag:met_<npc_id>=true in choice.actions[]. Otherwise the post-meet node is unreachable.")
	lines.append("")
	lines.append("EXAMPLE (mirror this pattern for every spawned NPC):")
	lines.append("  \"start_nodes\": [")
	lines.append("    { \"node\": \"start_remember\", \"requires\": { \"flag:met_silas\": \"true\" } },")
	lines.append("    { \"node\": \"start\", \"requires\": {} }")
	lines.append("  ],")
	lines.append("  \"dialog_tree\": {")
	lines.append("    \"start\": {")
	lines.append("      \"text\": \"A robed figure appraises you with cold eyes. 'Speak quickly.'\",")
	lines.append("      \"choices\": [")
	lines.append("        { \"id\": \"ask_about_deal\", \"text\": \"What deal went wrong?\",")
	lines.append("          \"actions\": [\"set_flag:met_silas=true\"], \"next\": \"deal_details\" }")
	lines.append("      ]")
	lines.append("    },")
	lines.append("    \"start_remember\": {")
	lines.append("      \"text\": \"He nods, a flicker of recognition. 'You again. Did you uncover anything?'\",")
	lines.append("      \"choices\": [ ... 1-3 follow-ups ... ]")
	lines.append("    }")
	lines.append("  }")
	lines.append("")
	lines.append("Order matters: start_nodes are evaluated TOP-TO-BOTTOM. Put the most-specific (most-restrictive `requires`) FIRST and the unconditional default LAST.")
	return "\n".join(lines) % [quest_giver_name, quest_giver_role, quest_giver_name, quest_giver_name]

# --------------------------------------------------------------------------
# CONTINUATION mode — fired mid-quest in response to a milestone event
# (npc_killed / npc_give). The LLM emits a small pack that adds new
# branches and patches existing NPC dialog. No new NPCs allowed.
# --------------------------------------------------------------------------

static func build_continuation_system_prompt(quest_giver_name: String,
		current_npc_names: Array) -> String:
	var lines: Array[String] = []
	lines.append("You write a CONTINUATION for an in-progress branching quest. The player just took a meaningful action; you respond by extending the story.")
	lines.append("")
	lines.append("Output ONE JSON object with EXACTLY these keys:")
	lines.append("{")
	lines.append("  \"new_branches\":     [ ... 1-2 Branch dicts ... ],")
	lines.append("  \"dialog_patches\":   [ ... 1-3 patches against EXISTING NPCs ... ],")
	lines.append("  \"trigger_flag\":     \"snake_case_flag_name\"   // engine sets flag:<this>=true after splicing so the new branches/dialog gate immediately.")
	lines.append("}")
	lines.append("")
	lines.append("Branch shape (same as the original bundle):")
	lines.append("  { \"id\", \"description\", \"requires_flags\":{}, \"objectives\":[...], \"rewards\":[...] }")
	lines.append("")
	lines.append("Dialog patch shape:")
	lines.append("  {")
	lines.append("    \"npc_name\":         \"<exact name from EXISTING NPCS>\",")
	lines.append("    \"new_nodes\":        { \"node_id\": { \"text\": \"...\", \"choices\":[...] }, ... },")
	lines.append("    \"new_start_nodes\":  [ { \"node\": \"node_id\", \"requires\":{} }, ... ]")
	lines.append("  }")
	lines.append("  - new_start_nodes are PREPENDED so the most-specific is checked first.")
	lines.append("  - Use the SAME predicate/action DSL as before (set_flag, take_player, memory:NPC.field, etc.).")
	lines.append("")
	lines.append("EXISTING NPCS (only reference these — DO NOT spawn new):")
	lines.append("  " + ", ".join(current_npc_names))
	lines.append("  Quest-giver: " + quest_giver_name)
	lines.append("")
	lines.append("ITEMS (closed catalog): " + ", ".join(WorldCatalog.item_ids()))
	lines.append("")
	lines.append("RULES:")
	lines.append("  - REQUIRED: emit AT LEAST 1 new_branch (max 2). Without it the player has nothing to do next.")
	lines.append("  - Each branch has ≥1 objective and ≥1 reward.")
	lines.append("  - Branch ids must be UNIQUE (don't reuse any existing branch id).")
	lines.append("  - Branches reference ONLY NPCs from EXISTING NPCS and items from ITEMS.")
	lines.append("  - dialog_patches add NEW node ids only (don't overwrite existing nodes by id).")
	lines.append("  - The story should ESCALATE: introduce a new pressure (a witness, a debt, a betrayal, a guilt) that flows from what the player just did.")
	lines.append("  - Strict JSON. No prose. First char `{`, last char `}`.")
	return "\n".join(lines)

static func build_continuation_user_prompt(quest_summary: Dictionary,
		event_kind: String, event_payload: Dictionary) -> String:
	var lines: Array[String] = []
	lines.append("CURRENT QUEST: " + String(quest_summary.get("title","")) + " — " + String(quest_summary.get("description","")))
	var existing_branch_ids: Array = []
	for b in quest_summary.get("branches", []):
		existing_branch_ids.append(String((b as Dictionary).get("id","")))
	lines.append("EXISTING BRANCH IDS (do not duplicate): " + ", ".join(existing_branch_ids))
	lines.append("")
	lines.append("EVENT: " + event_kind)
	for k in event_payload.keys():
		lines.append("  " + String(k) + ": " + String(event_payload[k]))
	lines.append("")
	lines.append("Write the continuation JSON now.")
	return "\n".join(lines)

# --------------------------------------------------------------------------
# ORCHESTRATION mode — Wanderer reads the player's action ledger and either
# emits a continuation chapter (full new quest bundle) or a closing
# epilogue. Single LLM call per Wanderer-talk.
# --------------------------------------------------------------------------

static func build_orchestration_system_prompt(quest_giver_name: String,
		current_npc_names: Array, max_remaining: int) -> String:
	var lines: Array[String] = []
	lines.append("You are the village's storyteller (the NPC '%s'). The player is on an active branching quest you previously gave them. They have just walked back to you to report what they've done." % quest_giver_name)
	lines.append("")
	lines.append("Your job: read the action ledger and the previous quest's premise, then DECIDE one of two things:")
	lines.append("  - 'continue' : the central conflict is unresolved. Issue a NEW chapter (full quest bundle) that picks up the threads — including any UNEXPECTED actions the player took. Treat unexpected actions as creative seeds, NEVER as fail conditions: a surprise kill becomes a new villain reveal, a theft becomes a heist subplot, a dialog twist becomes new lore.")
	lines.append("  - 'complete' : the player has resolved or definitively closed the central conflict. Emit a closing epilogue with rewards.")
	lines.append("")
	lines.append("Output ONE JSON object with EXACTLY these keys:")
	lines.append("{")
	lines.append("  \"decision\":         \"continue\" | \"complete\",")
	lines.append("  \"wanderer_dialog\":  \"2-4 sentences in your voice — your reaction to what the player did. Mandatory.\",")
	lines.append("  \"memory_claims\":    [ ... optional, see below ... ],")
	lines.append("  \"new_quest\":        {full quest+npcs+items bundle, same shape as branching bundle}   // ONLY if decision=continue")
	lines.append("  \"rewards\":          [ {\"item_id\": \"...\", \"count\": int} ]                         // ONLY if decision=complete")
	lines.append("}")
	lines.append("")
	lines.append("MEMORY CLAIMS (optional but encouraged when wanderer_dialog references the player's past actions):")
	lines.append("  Each claim describes ONE action the wanderer's dialog references. The engine cross-checks claims against the action ledger (the actions you can see above) for factual accuracy.")
	lines.append("  Claim shape: { \"kind\": \"kill_npc\"|\"npc_give\"|\"npc_take\"|\"dialog_choice\", \"params\": {...subset of the ledger entry's params...} }")
	lines.append("  Examples:")
	lines.append("    \"I heard you killed Silas.\"  →  { \"kind\": \"kill_npc\", \"params\": { \"npc_name\": \"Silas\" } }")
	lines.append("    \"You gave the gem to the priest.\"  →  { \"kind\": \"npc_give\", \"params\": { \"npc_name\": \"Priest\", \"item_id\": \"gem_red\" } }")
	lines.append("  Only emit a claim for actions that ACTUALLY appear in the ledger. Don't invent.")
	lines.append("  If wanderer_dialog doesn't reference any specific past action, omit memory_claims or use [].")
	lines.append("")
	lines.append("PACING: at most %d more continuations remain before the engine forces a closing. Pace your story arc accordingly." % max_remaining)
	lines.append("")
	lines.append("CONTINUATION REQUIREMENTS — when decision='continue':")
	lines.append("  - new_quest.npcs MUST contain AT LEAST 1 NEW NPC the player hasn't met yet (a name not in EXISTING NPCS list above).")
	lines.append("    Empty npcs[] makes the chapter feel hollow — the player has nothing fresh to interact with.")
	lines.append("  - Spawn 2-3 new NPCs ideally: a new antagonist or witness, a new ally or victim, etc.")
	lines.append("  - Existing NPCs may still be referenced in the new chapter's objectives, but they can't be the ONLY content.")
	if max_remaining <= 1:
		lines.append("  → STRONGLY prefer 'complete' this turn; the arc is at its end.")
	lines.append("")
	lines.append("Existing NPCs (continuation may reuse, kill, or replace them by spawning new ones in new_quest.npcs):")
	for nm in current_npc_names: lines.append("  - " + String(nm))
	lines.append("")
	# Continuation branch must follow the same rules as the original bundle —
	# reuse the branching schema verbatim by inlining the system prompt.
	lines.append("WHEN decision='continue', new_quest MUST follow this schema:")
	lines.append(build_system_prompt(false))
	lines.append("")
	lines.append("Strict JSON. First char `{`, last char `}`. No markdown.")
	return "\n".join(lines)

static func build_orchestration_user_prompt(prev_quest_summary: Dictionary,
		ledger: Array) -> String:
	var lines: Array[String] = []
	lines.append("PREVIOUS QUEST: " + String(prev_quest_summary.get("title","")) + " — " + String(prev_quest_summary.get("description","")))
	var brs: Array = prev_quest_summary.get("branches", [])
	if not brs.is_empty():
		lines.append("PREVIOUS BRANCHES (advisory only — they did NOT auto-complete the quest):")
		for b in brs:
			lines.append("  - " + String((b as Dictionary).get("id","")) + ": " + String((b as Dictionary).get("description","")))
	lines.append("")
	lines.append("ACTION LEDGER (what the player has actually done, oldest → newest):")
	if ledger.is_empty():
		lines.append("  (none — but player still walked back; respond accordingly)")
	else:
		for entry in ledger:
			var d: Dictionary = entry
			var k: String = String(d.get("kind",""))
			var p: Dictionary = d.get("params", {})
			var pretty := ""
			match k:
				"kill_npc":
					pretty = "killed %s" % String(p.get("npc_name","?"))
				"npc_give":
					pretty = "gave %s to %s" % [String(p.get("item_id","?")), String(p.get("npc_name","?"))]
				"npc_take":
					pretty = "took %s from %s" % [String(p.get("item_id","?")), String(p.get("npc_name","?"))]
				"dialog_choice":
					pretty = "picked '%s' with %s" % [String(p.get("choice_id","?")), String(p.get("npc_name","?"))]
				_:
					pretty = "%s %s" % [k, JSON.stringify(p)]
			lines.append("  - " + pretty)
	lines.append("")
	lines.append("Decide and emit the JSON now.")
	return "\n".join(lines)

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
