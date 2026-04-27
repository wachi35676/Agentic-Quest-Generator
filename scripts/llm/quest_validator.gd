class_name QuestValidator
extends RefCounted

# Pure validator. Takes a parsed Dictionary (the LLM bundle), returns an
# Array[String] of human-readable error messages. Empty array = valid.
#
# Same rules used by the live game and the offline fixture tests, so a
# fixture that passes here is guaranteed loadable.

# Continuation pack validator. Smaller schema than the full bundle;
# reuses the same per-objective/predicate helpers. Returns Array of error
# strings. extra_known_npcs is the set of NPC names that may be referenced.
static func validate_continuation(pack: Dictionary, extra_known_npcs: Array) -> Array:
	var errors: Array = []
	var npcs: Dictionary = {}
	for nm in extra_known_npcs: npcs[String(nm)] = true
	var item_set := {}
	for id in WorldCatalog.item_ids(): item_set[id] = true
	var obj_type_set := {}
	for t in WorldCatalog.OBJECTIVE_TYPES: obj_type_set[t] = true
	var action_prefix_set := {}
	for a in WorldCatalog.ACTION_PREFIXES: action_prefix_set[a] = true
	var action_bare_set := {}
	for a in WorldCatalog.ACTION_BARE: action_bare_set[a] = true
	var pred_prefix_set := {}
	for p in WorldCatalog.PREDICATE_PREFIXES: pred_prefix_set[p] = true
	var seen_branch_ids := {}
	for b in pack.get("new_branches", []):
		var bid: String = String(b.get("id",""))
		if bid == "":
			errors.append("cont: a branch is missing 'id'")
		elif seen_branch_ids.has(bid):
			errors.append("cont: duplicate branch id '%s'" % bid)
		else:
			seen_branch_ids[bid] = true
		if (b.get("objectives", []) as Array).is_empty():
			errors.append("cont: branch '%s' has no objectives" % bid)
		if (b.get("rewards", []) as Array).is_empty():
			errors.append("cont: branch '%s' has no rewards" % bid)
		for o in b.get("objectives", []):
			_check_objective(o, obj_type_set, item_set, npcs, errors)
		for r in b.get("rewards", []):
			_check_reward(r, item_set, errors)
	# dialog_patches
	for patch in pack.get("dialog_patches", []):
		var nm: String = String(patch.get("npc_name",""))
		if not npcs.has(nm):
			errors.append("cont: dialog_patch references unknown npc '%s'" % nm)
			continue
		var nodes: Variant = patch.get("new_nodes", {})
		if not (nodes is Dictionary):
			errors.append("cont: dialog_patch.new_nodes must be a dict")
			continue
		var node_ids := {}
		for nid in (nodes as Dictionary).keys():
			node_ids[String(nid)] = true
			var node: Dictionary = (nodes as Dictionary)[nid]
			for c in node.get("choices", []):
				_check_predicates(c.get("requires", {}), pred_prefix_set, "", item_set, npcs,
						"cont patch '%s' choice" % nm, errors)
				for a in c.get("actions", []):
					_check_action(String(a), action_prefix_set, action_bare_set, item_set,
							"cont patch '%s' choice action" % nm, errors)
		for sn in patch.get("new_start_nodes", []):
			var nid2: String = String(sn.get("node",""))
			if not node_ids.has(nid2):
				errors.append("cont patch '%s' start_node '%s' is not in new_nodes" % [nm, nid2])
			_check_predicates(sn.get("requires", {}), pred_prefix_set, "", item_set, npcs,
					"cont patch '%s' start_nodes" % nm, errors)
	return errors

static func validate(bundle: Dictionary, extra_known_npcs: Array = []) -> Array:
	var errors: Array = []

	if not bundle.has("quest"):
		errors.append("missing top-level key 'quest'")
		return errors
	if not bundle.has("npcs"):
		errors.append("missing top-level key 'npcs'")
		return errors

	var quest: Dictionary = bundle.get("quest", {})
	var npcs: Array = bundle.get("npcs", [])
	var items: Array = bundle.get("items", [])

	# Catalogs
	var item_set := {}
	for id in WorldCatalog.item_ids():
		item_set[id] = true
	var sheet_set := {}
	for s in WorldCatalog.character_sheets():
		sheet_set[s] = true
	var pos_set := {}
	for p in WorldCatalog.POSITION_HINTS:
		pos_set[p] = true
	var obj_type_set := {}
	for t in WorldCatalog.OBJECTIVE_TYPES:
		obj_type_set[t] = true
	var action_prefix_set := {}
	for a in WorldCatalog.ACTION_PREFIXES:
		action_prefix_set[a] = true
	var action_bare_set := {}
	for a in WorldCatalog.ACTION_BARE:
		action_bare_set[a] = true
	var pred_prefix_set := {}
	for p in WorldCatalog.PREDICATE_PREFIXES:
		pred_prefix_set[p] = true

	# --- quest header ---
	var qid: String = String(quest.get("id", ""))
	if qid == "":
		errors.append("quest.id is empty")
	elif not _is_id(qid):
		errors.append("quest.id '%s' must be lowercase a-z, digits, hyphens or underscores" % qid)
	if String(quest.get("title","")).length() > 80:
		errors.append("quest.title exceeds 80 chars")

	var branches: Array = quest.get("branches", [])
	if branches.size() < 3:
		errors.append("quest.branches must have at least 3 entries (got %d)" % branches.size())
	# fail_conditions are no longer required: orchestrator-managed quests
	# bypass evaluate() entirely, so fail conditions are advisory at best
	# and used to outright break the new Wanderer flow.
	var _fails: Array = quest.get("fail_conditions", [])

	# Branch ids unique + each has rewards + objectives
	var seen_branch_ids := {}
	for b in branches:
		var bid: String = String(b.get("id",""))
		if bid == "":
			errors.append("a branch is missing 'id'")
		elif seen_branch_ids.has(bid):
			errors.append("duplicate branch id '%s'" % bid)
		else:
			seen_branch_ids[bid] = true
		if b.get("objectives", []).is_empty():
			errors.append("branch '%s' has no objectives" % bid)
		if b.get("rewards", []).is_empty():
			errors.append("branch '%s' has no rewards" % bid)

	# --- gather referenced npc names ---
	var npc_names := {}
	for n in npcs:
		var name: String = String(n.get("npc_name",""))
		if name == "":
			errors.append("an npc is missing 'npc_name'")
		elif npc_names.has(name):
			errors.append("duplicate npc_name '%s'" % name)
		else:
			npc_names[name] = true
	# Caller-supplied NPCs that exist in the world but not in npcs[]
	# (e.g. the hand-placed quest-giver). Objectives may reference them.
	for extra in extra_known_npcs:
		npc_names[String(extra)] = true

	# --- objectives across primary + branches + fails ---
	var all_obj_lists := [quest.get("objectives", [])]
	for b in branches:
		all_obj_lists.append(b.get("objectives", []))
	all_obj_lists.append(_fails)
	for objs in all_obj_lists:
		for o in objs:
			_check_objective(o, obj_type_set, item_set, npc_names, errors)

	# --- rewards ---
	for r in quest.get("rewards", []):
		_check_reward(r, item_set, errors)
	for b in branches:
		for r in b.get("rewards", []):
			_check_reward(r, item_set, errors)

	# --- npcs ---
	for n in npcs:
		_check_npc(n, sheet_set, pos_set, item_set, action_prefix_set,
				   action_bare_set, pred_prefix_set, qid, npc_names, errors)

	# --- world items ---
	for it in items:
		var iid: String = String(it.get("id",""))
		if not item_set.has(iid):
			errors.append("items[].id '%s' is not in catalog" % iid)
		var ph: String = String(it.get("position_hint","center"))
		if not pos_set.has(ph):
			errors.append("items[].position_hint '%s' is not a valid hint" % ph)

	return errors

# ---- helpers ----

const _ID_CHARS := "abcdefghijklmnopqrstuvwxyz0123456789-_"

static func _is_id(s: String) -> bool:
	if s.length() == 0:
		return false
	for c in s:
		if not _ID_CHARS.contains(c):
			return false
	return true

static func _check_objective(o: Dictionary, types: Dictionary, item_set: Dictionary,
		npcs: Dictionary, errors: Array) -> void:
	var t: String = String(o.get("type",""))
	if not types.has(t):
		errors.append("objective.type '%s' not in %s" % [t, types.keys()])
		return
	var p: Dictionary = o.get("params", {})
	match t:
		"collect", "drop":
			var iid: String = String(p.get("item_id",""))
			if iid == "" or not item_set.has(iid):
				errors.append("objective '%s' params.item_id '%s' invalid" % [t, iid])
		"give", "take":
			var npc: String = String(p.get("npc_name",""))
			var iid2: String = String(p.get("item_id",""))
			if npc == "" or not npcs.has(npc):
				errors.append("objective '%s' references unknown npc '%s'" % [t, npc])
			if iid2 == "" or not item_set.has(iid2):
				errors.append("objective '%s' params.item_id '%s' invalid" % [t, iid2])
		"talk", "kill_npc":
			var nm: String = String(p.get("npc_name",""))
			if nm == "" or not npcs.has(nm):
				errors.append("objective '%s' references unknown npc '%s'" % [t, nm])
		"dialog_choice":
			var nm2: String = String(p.get("npc_name",""))
			var cid: String = String(p.get("choice_id",""))
			if nm2 == "" or not npcs.has(nm2):
				errors.append("objective 'dialog_choice' references unknown npc '%s'" % nm2)
			if cid == "":
				errors.append("objective 'dialog_choice' missing params.choice_id")
		"kill_enemy":
			pass   # enemy_type is open-ended for v1
		"reach":
			pass

static func _check_reward(r: Dictionary, item_set: Dictionary, errors: Array) -> void:
	var iid: String = String(r.get("item_id",""))
	if iid == "" or not item_set.has(iid):
		errors.append("reward.item_id '%s' is not in catalog" % iid)

static func _check_npc(n: Dictionary, sheets: Dictionary, positions: Dictionary,
		item_set: Dictionary, action_prefixes: Dictionary, action_bare: Dictionary,
		pred_prefixes: Dictionary, qid: String, all_npcs: Dictionary,
		errors: Array) -> void:
	var name: String = String(n.get("npc_name",""))
	var sheet: String = String(n.get("character_sheet",""))
	if not sheets.has(sheet):
		errors.append("npc '%s' character_sheet '%s' not in %s" % [name, sheet, sheets.keys()])
	var ph: String = String(n.get("position_hint","center"))
	if not positions.has(ph):
		errors.append("npc '%s' position_hint '%s' invalid" % [name, ph])
	for inv in n.get("initial_items", []):
		var iid: String = String(inv.get("id",""))
		if not item_set.has(iid):
			errors.append("npc '%s' initial_items has unknown id '%s'" % [name, iid])
	var dt: Dictionary = n.get("dialog_tree", {})
	var node_ids := {}
	for k in dt.keys():
		node_ids[String(k)] = true
	# dialog_start exists
	var ds: String = String(n.get("dialog_start","start"))
	if not node_ids.has(ds):
		errors.append("npc '%s' dialog_start '%s' is not a node" % [name, ds])
	# start_nodes references
	for sn in n.get("start_nodes", []):
		var nid: String = String(sn.get("node",""))
		if not node_ids.has(nid):
			errors.append("npc '%s' start_nodes references missing node '%s'" % [name, nid])
		_check_predicates(sn.get("requires", {}), pred_prefixes, qid, item_set, all_npcs,
				"npc '%s' start_nodes" % name, errors)
	# Each node's choices
	for nid in dt.keys():
		var node: Dictionary = dt[nid]
		for c in node.get("choices", []):
			var nxt: String = String(c.get("next",""))
			# "__expand__" is a valid sentinel for lazy generation — the agent
			# will produce the next node on demand or via prefetch.
			if nxt != "" and nxt != "end" and nxt != "__expand__" and not node_ids.has(nxt):
				errors.append("npc '%s' node '%s' choice next '%s' missing" % [name, nid, nxt])
			_check_predicates(c.get("requires", {}), pred_prefixes, qid, item_set, all_npcs,
					"npc '%s' node '%s' choice" % [name, nid], errors)
			for a in c.get("actions", []):
				_check_action(String(a), action_prefixes, action_bare, item_set,
						"npc '%s' node '%s' choice action" % [name, nid], errors)

static func _check_predicates(req: Dictionary, prefixes: Dictionary, qid: String,
		item_set: Dictionary, all_npcs: Dictionary, where: String, errors: Array) -> void:
	for k in req.keys():
		var key: String = String(k)
		var prefix := ""
		var rest: String = key
		var ci: int = key.find(":")
		if ci > 0:
			prefix = key.substr(0, ci)
			rest = key.substr(ci + 1)
		if prefix != "" and not prefixes.has(prefix):
			errors.append("%s requires-key '%s' has unknown prefix" % [where, key])
		match prefix:
			"inv":
				if not item_set.has(rest):
					errors.append("%s inv:%s — item not in catalog" % [where, rest])
			"memory":
				var dot: int = rest.find(".")
				if dot <= 0:
					errors.append("%s memory key '%s' missing 'NPC.field' form" % [where, rest])
				else:
					var nm: String = rest.substr(0, dot)
					if not all_npcs.has(nm):
						errors.append("%s memory references unknown npc '%s'" % [where, nm])
			"quest":
				if rest != qid:
					# Allowed but warn — usually a typo.
					pass

static func _check_action(action: String, prefixes: Dictionary, bare: Dictionary,
		item_set: Dictionary, where: String, errors: Array) -> void:
	if ":" in action:
		var parts := action.split(":", false, 1)
		var verb: String = parts[0]
		var arg: String = parts[1]
		if not prefixes.has(verb):
			errors.append("%s action verb '%s' unknown" % [where, verb])
		match verb:
			"give_player", "take_player":
				if not item_set.has(arg):
					errors.append("%s action '%s' item '%s' not in catalog" % [where, verb, arg])
			"set_flag", "remember":
				if not ("=" in arg):
					errors.append("%s action '%s:%s' missing 'key=value'" % [where, verb, arg])
	else:
		if not bare.has(action):
			errors.append("%s bare action '%s' unknown" % [where, action])
