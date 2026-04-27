class_name QuestSanitizer
extends RefCounted

# Deterministic cleanup of common qwen3:14b output quirks before validation.
# Each pass returns the (possibly mutated) bundle plus a list of fix notes
# that we log so we can see what the model actually emitted vs what we
# coerced it into. The validator runs AFTER this — anything still wrong
# falls into the repair loop as a real prompt error.

# Sanitize a continuation pack (small schema: new_branches + dialog_patches).
# Reuses the same per-objective and per-action cleaners as the full
# bundle. Returns { bundle (the cleaned pack), notes }.
static func sanitize_continuation(pack: Variant, current_npc_names: Array) -> Dictionary:
	var notes: Array = []
	if not (pack is Dictionary):
		return {"bundle": pack, "notes": notes}
	var p: Dictionary = pack
	# Build a case-insensitive lookup from lowercase -> canonical name.
	# The LLM frequently emits the quest-giver as 'wanderer' instead of
	# 'Wanderer'; without normalization the validator drops every branch
	# referencing them.
	var npc_set: Dictionary = {}
	var npc_canon: Dictionary = {}
	for nm in current_npc_names:
		var s: String = String(nm)
		npc_set[s] = true
		npc_canon[s.to_lower()] = s
	# 1. Clean new_branches via the same per-branch logic as the full
	#    bundle. Re-using _clean_quest indirectly is overkill; do the
	#    minimum: ASCII ids, predicate keys, drop empty/objectiveless,
	#    drop branches that reference unknown NPCs / items.
	var cleaned_branches: Array = []
	for b in p.get("new_branches", []):
		# Defensive: model occasionally emits strings instead of dicts.
		if not (b is Dictionary):
			notes.append("cont: drop non-dict branch entry")
			continue
		var bid: String = _ascii_id(String(b.get("id","")))
		b["id"] = bid
		_clean_predicates(b.get("requires_flags", {}), notes, "cont.branch.requires_flags")
		var clean_objs: Array = []
		for o in b.get("objectives", []):
			if not (o is Dictionary):
				notes.append("cont: drop non-dict objective in branch '%s'" % bid)
				continue
			_clean_objective(o, notes)
			if not (String(o.get("type","")) in _OBJECTIVE_TYPES):
				notes.append("cont: drop objective with bad type")
				continue
			var params: Dictionary = o.get("params", {})
			var nm: String = String(params.get("npc_name",""))
			if nm != "":
				if npc_canon.has(nm.to_lower()):
					var canon: String = npc_canon[nm.to_lower()]
					if canon != nm:
						params["npc_name"] = canon
						notes.append("cont: npc_name '%s' -> '%s' (case fix)" % [nm, canon])
				elif not npc_set.has(nm):
					notes.append("cont: drop objective referencing unknown npc '%s'" % nm)
					continue
			clean_objs.append(o)
		b["objectives"] = clean_objs
		# Filter rewards to dicts only.
		var clean_rewards: Array = []
		for r in b.get("rewards", []):
			if r is Dictionary: clean_rewards.append(r)
		b["rewards"] = clean_rewards
		if clean_objs.is_empty() or clean_rewards.is_empty():
			notes.append("cont: drop branch '%s' (no objectives or rewards)" % bid)
			continue
		cleaned_branches.append(b)
	# Enforce ≥2 objectives per continuation branch (report-back if needed).
	if not current_npc_names.is_empty():
		var giver: String = String(current_npc_names[-1])  # quest-giver appended last
		# Actually look for a more reliable signal: if the caller passed
		# the quest-giver name, it's typically the last extra_known entry.
		# Fall back to the first if needed.
		if giver == "": giver = String(current_npc_names[0])
		for b in cleaned_branches:
			if (b.get("objectives", []) as Array).size() >= 2: continue
			b["objectives"] = (b.get("objectives", []) as Array) + [{
				"type": "talk",
				"params": {"npc_name": giver},
				"required": 1,
				"description": "Report back to %s." % giver,
			}]
			notes.append("cont: branch '%s' appended report-back to %s" % [
					String(b.get("id","?")), giver])
	p["new_branches"] = cleaned_branches
	# 2. Clean dialog_patches: drop patches against unknown NPCs; clean
	#    actions inside choices; clean predicate keys; ensure new_nodes
	#    is a Dictionary; ensure new_start_nodes is an Array.
	var cleaned_patches: Array = []
	for patch in p.get("dialog_patches", []):
		if not (patch is Dictionary):
			notes.append("cont: drop non-dict dialog_patch")
			continue
		var nm2: String = String(patch.get("npc_name",""))
		if npc_canon.has(nm2.to_lower()):
			var canon2: String = npc_canon[nm2.to_lower()]
			if canon2 != nm2:
				patch["npc_name"] = canon2
				nm2 = canon2
				notes.append("cont: dialog_patch npc '%s' -> '%s' (case fix)" % [String(patch.get("npc_name","")), canon2])
		elif not npc_set.has(nm2):
			notes.append("cont: drop dialog_patch for unknown npc '%s'" % nm2)
			continue
		var nodes: Variant = patch.get("new_nodes", {})
		if not (nodes is Dictionary):
			patch["new_nodes"] = {}
		else:
			for nid in (nodes as Dictionary).keys():
				var node: Dictionary = (nodes as Dictionary)[nid]
				for c in node.get("choices", []):
					if c is Dictionary:
						var dc: Dictionary = c
						var ocid: String = String(dc.get("id",""))
						var ncid: String = _ascii_id(ocid)
						if ncid != "" and ncid != ocid:
							dc["id"] = ncid
						var acts: Array = dc.get("actions", [])
						var clean: Array = []
						for a in acts:
							var ca: String = _clean_action(String(a))
							if ca != "": clean.append(ca)
						dc["actions"] = clean
						_clean_predicates(dc.get("requires", {}), notes, "cont.choice.requires")
		var sns: Variant = patch.get("new_start_nodes", [])
		if sns is Array:
			for sn in sns:
				if sn is Dictionary:
					_clean_predicates((sn as Dictionary).get("requires", {}), notes, "cont.start_nodes.requires")
		cleaned_patches.append(patch)
	p["dialog_patches"] = cleaned_patches
	# 3. trigger_flag — ASCII-clean.
	if p.has("trigger_flag"):
		p["trigger_flag"] = _ascii_id(String(p["trigger_flag"]))
	return {"bundle": p, "notes": notes}

static func sanitize(bundle: Variant, drop_npc_names: Array = []) -> Dictionary:
	var notes: Array = []
	if not (bundle is Dictionary):
		return {"bundle": bundle, "notes": notes}
	var b: Dictionary = bundle
	# Case-fix npc_name references in objectives so a lowercase "wanderer"
	# resolves to the canonical "Wanderer" in extra_known.
	_normalize_npc_name_case_in_objectives(b, drop_npc_names, notes)
	# Drop objectives whose npc_name doesn't resolve to any spawned or
	# pre-existing NPC. The model often hallucinates generic role names
	# ("villager", "guard") that aren't actual entities, and the validator
	# would otherwise reject the whole bundle.
	_drop_objectives_with_unknown_npcs(b, drop_npc_names, notes)
	# Force every branch to have a "report back" objective if the LLM
	# emitted a single-objective branch — otherwise a one-kill or one-give
	# completes the entire quest instantly, which feels broken.
	_ensure_branch_report_back(b, drop_npc_names, notes)
	# Drop NPCs whose name collides with a hand-placed world NPC (e.g. the
	# quest-giver). The model sometimes re-emits them in npcs[] despite the
	# prompt, which causes a phantom duplicate to spawn.
	if not drop_npc_names.is_empty():
		var drop_set: Dictionary = {}
		for n in drop_npc_names: drop_set[String(n)] = true
		var kept: Array = []
		for npc in b.get("npcs", []):
			var nm: String = String(npc.get("npc_name",""))
			if drop_set.has(nm):
				notes.append("dropping bundle-NPC '%s' (collides with hand-placed quest-giver)" % nm)
				continue
			kept.append(npc)
		b["npcs"] = kept
	# An NPC that needs to be alive for ANY objective (give/take/talk/
	# dialog_choice) must NEVER die from a dialog action — that softlocks
	# the quest. Build the protected set here.
	var protected: Dictionary = {}
	var quest: Dictionary = b.get("quest", {})
	for o in _all_objectives(quest):
		var t: String = String(o.get("type",""))
		if t in ["give","take","talk","dialog_choice"]:
			var nm: String = String((o.get("params", {}) as Dictionary).get("npc_name",""))
			if nm != "": protected[nm] = true
	_clean_quest(quest, notes)
	for npc in b.get("npcs", []):
		_clean_npc(npc, notes)
		# Strip 'die' actions from protected NPCs' dialog choices — they
		# need to remain interactable for the player to advance branches.
		var nm: String = String(npc.get("npc_name",""))
		if protected.has(nm):
			_strip_die_actions(npc, notes)
	return {"bundle": b, "notes": notes}

static func _drop_objectives_with_unknown_npcs(bundle: Dictionary,
		extra_known_npcs: Array, notes: Array) -> void:
	# Build the canonical set of "real" NPCs: extra_known (the hand-placed
	# quest-giver) + the bundle's spawned npcs[]. Any objective whose
	# npc_name doesn't resolve to one of those gets dropped.
	var known: Dictionary = {}
	for nm in extra_known_npcs:
		known[String(nm)] = true
	for n in bundle.get("npcs", []):
		var s: String = String((n as Dictionary).get("npc_name",""))
		if s != "": known[s] = true
	var quest: Dictionary = bundle.get("quest", {})
	# Walk every objective container and filter.
	var filter_lists: Array = ["objectives", "fail_conditions"]
	for k in filter_lists:
		var arr: Array = quest.get(k, [])
		var kept: Array = []
		for o in arr:
			if not (o is Dictionary): continue
			var nm: String = String((o as Dictionary).get("params", {}).get("npc_name",""))
			if nm == "" or known.has(nm):
				kept.append(o)
			else:
				notes.append("drop %s objective: unknown npc '%s'" % [k, nm])
		quest[k] = kept
	# Branch objectives.
	for b in quest.get("branches", []):
		if not (b is Dictionary): continue
		var bobjs: Array = (b as Dictionary).get("objectives", [])
		var bkept: Array = []
		for o in bobjs:
			if not (o is Dictionary): continue
			var nm2: String = String((o as Dictionary).get("params", {}).get("npc_name",""))
			if nm2 == "" or known.has(nm2):
				bkept.append(o)
			else:
				notes.append("drop branch '%s' objective: unknown npc '%s'" % [
						String((b as Dictionary).get("id","?")), nm2])
		(b as Dictionary)["objectives"] = bkept

static func _ensure_branch_report_back(bundle: Dictionary,
		extra_known_npcs: Array, notes: Array) -> void:
	# Pick the canonical quest-giver name. extra_known_npcs is supplied
	# by the agent (the hand-placed Wanderer for branching quests). Skip
	# if no giver is known — we can't report back to nobody.
	if extra_known_npcs.is_empty(): return
	var giver: String = String(extra_known_npcs[0])
	var quest: Dictionary = bundle.get("quest", {})
	for b in quest.get("branches", []):
		if not (b is Dictionary): continue
		var objs: Array = (b as Dictionary).get("objectives", [])
		if objs.size() >= 2: continue
		# Would adding a talk:giver create a duplicate? Skip if the only
		# existing objective is already that talk.
		if objs.size() == 1 and (objs[0] is Dictionary):
			var only: Dictionary = objs[0]
			var t: String = String(only.get("type",""))
			var nm: String = String((only.get("params", {}) as Dictionary).get("npc_name",""))
			if t == "talk" and nm == giver:
				continue
		objs.append({
			"type": "talk",
			"params": {"npc_name": giver},
			"required": 1,
			"description": "Report back to %s." % giver,
		})
		(b as Dictionary)["objectives"] = objs
		notes.append("branch '%s': appended talk:%s report-back objective" % [
				String((b as Dictionary).get("id","?")), giver])

static func _normalize_npc_name_case_in_objectives(bundle: Dictionary,
		extra_known_npcs: Array, notes: Array) -> void:
	# Build canonical-case lookup: lowercase -> canonical. Includes both
	# extra_known (the hand-placed quest-giver) and the bundle's own
	# spawned npcs[] so cross-references work either direction.
	var canon: Dictionary = {}
	for nm in extra_known_npcs:
		canon[String(nm).to_lower()] = String(nm)
	for n in bundle.get("npcs", []):
		var s: String = String((n as Dictionary).get("npc_name",""))
		if s != "": canon[s.to_lower()] = s
	# Walk every objective container.
	var quest: Dictionary = bundle.get("quest", {})
	var lists: Array = [quest.get("objectives", []), quest.get("fail_conditions", [])]
	for b in quest.get("branches", []):
		lists.append((b as Dictionary).get("objectives", []))
	for arr in lists:
		for o in arr:
			if not (o is Dictionary): continue
			var p: Dictionary = (o as Dictionary).get("params", {})
			var nm: String = String(p.get("npc_name",""))
			if nm == "": continue
			if canon.has(nm.to_lower()):
				var c: String = canon[nm.to_lower()]
				if c != nm:
					p["npc_name"] = c
					notes.append("npc_name '%s' -> '%s' (case fix)" % [nm, c])

static func _all_objectives(quest: Dictionary) -> Array:
	var out: Array = []
	out.append_array(quest.get("objectives", []))
	for b in quest.get("branches", []):
		out.append_array(b.get("objectives", []))
	return out

static func _strip_die_actions(npc: Dictionary, notes: Array) -> void:
	var name: String = String(npc.get("npc_name","?"))
	var dt: Dictionary = npc.get("dialog_tree", {})
	var stripped: int = 0
	for nid in dt.keys():
		var node: Dictionary = dt[nid]
		for c in node.get("choices", []):
			var acts: Array = c.get("actions", [])
			var clean: Array = []
			for a in acts:
				if String(a) == "die":
					stripped += 1
					continue
				clean.append(a)
			c["actions"] = clean
	if stripped > 0:
		notes.append("npc '%s': stripped %d 'die' action(s) (NPC is needed for an objective)" % [name, stripped])

# ---- quest-level ----
const _OBJECTIVE_TYPES: PackedStringArray = ["collect","drop","give","take","talk","kill_enemy","kill_npc","dialog_choice","reach"]

static func _clean_quest(q: Dictionary, notes: Array) -> void:
	if q.is_empty(): return
	var oid: String = String(q.get("id",""))
	var nid: String = _ascii_id(oid)
	if nid != oid:
		notes.append("quest.id: '%s' -> '%s'" % [oid, nid])
		q["id"] = nid
	# Drop branches missing required pieces (objectives or rewards). The
	# model occasionally emits a `failed_quest` branch with no objectives,
	# which the validator rejects but the rest of the bundle is fine.
	var kept_branches: Array = []
	for b in q.get("branches", []):
		var obid: String = String(b.get("id",""))
		var nbid: String = _ascii_id(obid)
		if nbid != obid:
			notes.append("branch.id: '%s' -> '%s'" % [obid, nbid])
			b["id"] = nbid
		_clean_predicates(b.get("requires_flags", {}), notes, "branch.requires_flags")
		# Drop objectives with unknown types (e.g. `flag` — the model invents this).
		var clean_objs: Array = []
		for o in b.get("objectives", []):
			_clean_objective(o, notes)
			if String(o.get("type","")) in _OBJECTIVE_TYPES:
				clean_objs.append(o)
			else:
				notes.append("branch '%s': dropping objective with bad type '%s'" % [
						nbid, String(o.get("type",""))])
		b["objectives"] = clean_objs
		if clean_objs.is_empty():
			notes.append("branch '%s': dropped (no valid objectives left)" % nbid)
			continue
		if (b.get("rewards", []) as Array).is_empty():
			notes.append("branch '%s': dropped (no rewards)" % nbid)
			continue
		kept_branches.append(b)
	q["branches"] = kept_branches
	for o in q.get("objectives", []):
		_clean_objective(o, notes)
	# fail_conditions: drop bad-type objectives + drop fail conditions
	# whose target overlaps with any branch's objective. The model often
	# emits a `kill_npc:Silas` fail alongside a `kill_npc:Silas` branch
	# objective — killing Silas advances the branch by 1 step but ALSO
	# triggers the fail; the fail wins because the branch needs more
	# steps. Drop these contradictions.
	var branch_targets: Dictionary = {}   # "type|param_signature" -> true
	for b in q.get("branches", []):
		for o in b.get("objectives", []):
			branch_targets[_obj_key(o)] = true
	var clean_fails: Array = []
	for o in q.get("fail_conditions", []):
		_clean_objective(o, notes)
		if not (String(o.get("type","")) in _OBJECTIVE_TYPES):
			continue
		var k: String = _obj_key(o)
		if branch_targets.has(k):
			notes.append("fail_condition '%s' overlaps a branch objective — dropped" % k)
			continue
		clean_fails.append(o)
	q["fail_conditions"] = clean_fails

# Stable key for an objective: "<type>|<sorted params>". Used to detect
# overlap between fail conditions and branch objectives.
static func _obj_key(o: Dictionary) -> String:
	var t: String = String(o.get("type",""))
	var p: Dictionary = o.get("params", {})
	var keys: Array = p.keys()
	keys.sort()
	var pairs: Array = []
	for k in keys:
		pairs.append("%s=%s" % [String(k), String(p[k])])
	return "%s|%s" % [t, ",".join(pairs)]

static func _clean_objective(o: Dictionary, notes: Array) -> void:
	# choice_id and similar id-like params get ASCII-cleaned.
	var p: Dictionary = o.get("params", {})
	for k in ["choice_id"]:
		if p.has(k):
			var ov: String = String(p[k])
			var nv: String = _ascii_id(ov)
			if nv != ov:
				notes.append("objective.params.%s: '%s' -> '%s'" % [k, ov, nv])
				p[k] = nv

# ---- npc-level ----
static func _clean_npc(n: Dictionary, notes: Array) -> void:
	# Drop initial_items entries with item ids not in the catalog. The
	# LLM regularly invents items like "dagger" / "torch" / "rope" that
	# don't exist; without filtering, the validator rejects the bundle.
	var inv: Array = n.get("initial_items", [])
	if inv is Array and not inv.is_empty():
		var clean_inv: Array = []
		for entry in inv:
			if not (entry is Dictionary): continue
			var iid: String = String((entry as Dictionary).get("id",""))
			if ItemDB.has(iid):
				clean_inv.append(entry)
			else:
				notes.append("npc '%s' initial_items: drop unknown id '%s'" % [
						String(n.get("npc_name","?")), iid])
		n["initial_items"] = clean_inv
	# 1. character_sheet: snap to nearest roster entry. Pure Levenshtein
	# would map "Thug"->"Monk" by edit distance, which looks ridiculous;
	# prefer a role/keyword-driven pick first, fall back to distance.
	var sheets: Array = WorldCatalog.character_sheets()
	var sheet: String = String(n.get("character_sheet",""))
	if sheet != "" and not _has_ci(sheets, sheet):
		var role_hint: String = (sheet + " " + String(n.get("role",""))).to_lower()
		var snapped: String = _role_pick(role_hint, sheets)
		if snapped == "":
			snapped = _nearest(sheet, sheets)
		if snapped != "":
			notes.append("npc '%s' character_sheet '%s' -> '%s'" % [String(n.get("npc_name","?")), sheet, snapped])
			n["character_sheet"] = snapped

	# 2. dialog_tree: clean keys, choice ids, action verbs, predicate keys.
	var dt: Dictionary = n.get("dialog_tree", {})
	# rebuild with cleaned keys (preserve mapping so 'next' refs survive).
	var key_remap: Dictionary = {}
	var new_dt: Dictionary = {}
	for k in dt.keys():
		var ks: String = String(k)
		var nks: String = _ascii_id(ks)
		key_remap[ks] = nks
		new_dt[nks] = dt[k]
		if nks != ks:
			notes.append("dialog_tree key: '%s' -> '%s'" % [ks, nks])
	# Now sanitize each node's choices.
	for nid in new_dt.keys():
		var node: Dictionary = new_dt[nid]
		# Empty-choices nodes are dead-ends — the player is stuck on
		# Give/Take/Bye with no narrative progression. Inject a generic
		# "Tell me more" choice that lazy-expands into the next node so
		# the agent fills it on demand.
		if (node.get("choices", []) as Array).is_empty():
			var ntext: String = String(node.get("text",""))
			node["choices"] = [{
				"id": "tell_me_more",
				"text": "Tell me more.",
				"next": "__expand__",
				"next_hint": "Continue from: " + ntext.substr(0, 80),
			}]
			notes.append("npc '%s' node '%s': empty choices -> injected lazy-expand" % [
					String(n.get("npc_name","?")), String(nid)])
		for c in node.get("choices", []):
			# choice id
			var ocid: String = String(c.get("id",""))
			var ncid: String = _ascii_id(ocid)
			if ncid != ocid:
				notes.append("choice id: '%s' -> '%s'" % [ocid, ncid])
				c["id"] = ncid
			# next: remap if it pointed to a renamed key
			var nxt: String = String(c.get("next",""))
			if key_remap.has(nxt):
				var rm: String = key_remap[nxt]
				if rm != nxt:
					c["next"] = rm
					notes.append("choice.next: '%s' -> '%s'" % [nxt, rm])
			elif nxt != "" and nxt != "end" and nxt != "__expand__":
				# Orphan ref — coerce to __expand__ so lazy gen can fill it.
				if not new_dt.has(nxt):
					notes.append("choice.next '%s' is orphan -> __expand__" % nxt)
					c["next"] = "__expand__"
					if not c.has("next_hint") or String(c.get("next_hint","")) == "":
						c["next_hint"] = "continue from: " + String(c.get("text",""))
			# actions: clean each, DROP entries that come back empty
			# (unrecognised verbs sanitize to "" — keeping them as
			# empty strings makes the validator fail with "bare action ''").
			var acts: Array = c.get("actions", [])
			var clean_acts: Array = []
			for a in acts:
				var ca: String = _clean_action(String(a))
				if ca == "":
					notes.append("action: '%s' dropped" % a)
					continue
				if ca != String(a):
					notes.append("action: '%s' -> '%s'" % [a, ca])
				clean_acts.append(ca)
			c["actions"] = clean_acts
			# requires
			_clean_predicates(c.get("requires", {}), notes, "choice.requires")
	n["dialog_tree"] = new_dt

	# 3. dialog_start + start_nodes: remap to renamed keys, drop orphans.
	# start_nodes can't use __expand__ (it's resolved at conversation start
	# before the agent is reachable), so any reference to a non-existent node
	# is dropped rather than coerced. We always keep at least 'dialog_start'.
	if n.has("dialog_start"):
		var ds: String = String(n["dialog_start"])
		if key_remap.has(ds):
			n["dialog_start"] = key_remap[ds]
		if not new_dt.has(String(n["dialog_start"])):
			# The model named a dialog_start that doesn't exist. Pick the
			# first node we DO have, or fabricate a 'start' stub.
			var fallback: String = ""
			for k in new_dt.keys():
				fallback = String(k); break
			if fallback == "":
				fallback = "start"
				new_dt["start"] = {"text": "...", "choices": []}
			notes.append("npc '%s' dialog_start '%s' missing -> '%s'" % [
				String(n.get("npc_name","?")), String(n["dialog_start"]), fallback])
			n["dialog_start"] = fallback
	var kept_starts: Array = []
	for sn in n.get("start_nodes", []):
		var snn: String = String(sn.get("node",""))
		if key_remap.has(snn):
			sn["node"] = key_remap[snn]
			snn = String(sn["node"])
		_clean_predicates(sn.get("requires", {}), notes, "start_nodes.requires")
		if new_dt.has(snn):
			kept_starts.append(sn)
		else:
			notes.append("npc '%s' start_nodes '%s' missing -> dropped" % [
				String(n.get("npc_name","?")), snn])
	n["start_nodes"] = kept_starts
	# Always need a fallback start_node pointing at dialog_start.
	if kept_starts.is_empty():
		n["start_nodes"] = [{"node": String(n.get("dialog_start","start")), "requires": {}}]
	# Auto-inject `met_<npc>` flag handling so repeat visits don't replay
	# the intro. Only applied when the model didn't include any flag-gated
	# start_node — otherwise we'd clobber the LLM's intent.
	_ensure_met_flag(n, new_dt, notes)

# If the NPC's start_nodes are all unconditional (no flag/quest/memory
# predicates), set a `met_<npc>` flag on the first choice of dialog_start
# and prepend a generic `start_remember` node gated on that flag. The
# remember node text is a short stub the player will see only on repeat
# visits — not as good as a real LLM-emitted memory node, but better
# than replaying the same intro forever.
static func _ensure_met_flag(n: Dictionary, dt: Dictionary, notes: Array) -> void:
	var name: String = String(n.get("npc_name",""))
	if name == "": return
	var flag_key: String = "met_%s" % _ascii_id(name)
	# If any existing start_node already gates on a flag/memory/quest
	# predicate, the model is doing state tracking — don't interfere.
	for sn in n.get("start_nodes", []):
		var req: Dictionary = sn.get("requires", {})
		for k in req.keys():
			var ks: String = String(k)
			if ks.begins_with("flag:") or ks.begins_with("memory:") or ks.begins_with("quest:"):
				return
	# Add set_flag:met_<npc>=true to first choice of dialog_start (idempotent).
	var ds: String = String(n.get("dialog_start","start"))
	if dt.has(ds):
		var node: Dictionary = dt[ds]
		var choices: Array = node.get("choices", [])
		if not choices.is_empty():
			var first: Dictionary = choices[0]
			var acts: Array = first.get("actions", [])
			var has_set := false
			for a in acts:
				if String(a) == "set_flag:%s=true" % flag_key:
					has_set = true; break
			if not has_set:
				acts.append("set_flag:%s=true" % flag_key)
				first["actions"] = acts
				notes.append("npc '%s': injected set_flag:%s on first-meet choice" % [name, flag_key])
	# Add a `start_remember` node with a short greeting if not already there.
	if not dt.has("start_remember"):
		dt["start_remember"] = {
			"text": "%s glances up. 'You again.'" % name,
			"choices": [
				{"id": "continue", "text": "Let's talk.", "next": ds},
				{"id": "leave", "text": "Never mind.", "next": "end"},
			],
		}
		notes.append("npc '%s': injected fallback 'start_remember' node" % name)
	# Prepend a flag-gated start_node (most-specific FIRST per resolver order).
	var existing: Array = n.get("start_nodes", [])
	var new_starts: Array = []
	new_starts.append({"node": "start_remember", "requires": {"flag:%s" % flag_key: "true"}})
	for sn in existing:
		new_starts.append(sn)
	n["start_nodes"] = new_starts

# ---- helpers ----

# Strip non-ASCII, lowercase, replace spaces+dots with underscores, drop the
# rest of the disallowed chars. Keeps a-z, 0-9, hyphen, underscore.
static func _ascii_id(s: String) -> String:
	var lowered: String = s.to_lower().strip_edges()
	var out := ""
	for ch in lowered:
		var code: int = ch.unicode_at(0)
		if (code >= 97 and code <= 122) or (code >= 48 and code <= 57) or ch == "_" or ch == "-":
			out += ch
		elif ch == " " or ch == "." or ch == "/" or ch == "\\":
			out += "_"
		# else: drop (Chinese chars, punctuation, emoji, etc.)
	# collapse runs of underscores
	while "__" in out:
		out = out.replace("__", "_")
	return out.lstrip("_-").rstrip("_-")

# Removes whitespace inside an action string and around the colon, plus
# fixes the most common verb confusions the model makes:
#   memory:k=v   -> remember:k=v        (predicate-keyword used as action)
#   kill_npc:X   -> die                 (objective-type used as action)
#   quest:X=Y    -> set_flag:X=Y        (predicate prefix used as action)
# Returns the cleaned string. If the result is unrecognisable, returns ""
# so the caller can drop it.
const _VALID_ACTION_PREFIXES: PackedStringArray = ["give_player","take_player","set_flag","remember"]
const _VALID_BARE_ACTIONS: PackedStringArray = ["drop_inventory","die"]

static func _clean_action(a: String) -> String:
	var s: String = a.strip_edges().replace(" ", "").replace("\t", "")
	if s == "":
		return ""
	# Bare verb?
	if not (":" in s):
		if s in _VALID_BARE_ACTIONS:
			return s
		# Common alias the model emits.
		if s == "kill" or s == "death":
			return "die"
		return ""
	# verb:arg form
	var parts := s.split(":", false, 1)
	var verb: String = parts[0]
	var arg: String = parts[1]
	# Verb confusion fixes.
	if verb == "memory":
		verb = "remember"
	elif verb == "quest":
		verb = "set_flag"
	elif verb == "kill_npc" or verb == "kill":
		# 'kill_npc' is an objective type, not an action verb. Treat as die.
		return "die"
	if verb in _VALID_ACTION_PREFIXES:
		return "%s:%s" % [verb, arg]
	return ""

static func _clean_predicates(req: Dictionary, notes: Array, where: String) -> void:
	# Fix common malformed predicate keys:
	#   "flag : persuaded"          -> "flag:persuaded"      (whitespace)
	#   "memory:Elara:knows_x"      -> "memory:Elara.knows_x" (colon vs dot)
	#   "memory:Elara"              -> dropped                (missing field)
	var fixed: Dictionary = {}
	var changed := false
	for k in req.keys():
		var ks: String = String(k)
		var nks: String = ks.replace(" ", "").replace("\t", "")
		# memory keys must be `memory:NPC.field`, not `memory:NPC:field`.
		if nks.begins_with("memory:"):
			var rest: String = nks.substr(7)
			# Replace the FIRST colon in `rest` with a dot, if any.
			var ci: int = rest.find(":")
			if ci > 0:
				rest = rest.substr(0, ci) + "." + rest.substr(ci + 1)
				nks = "memory:" + rest
			# Drop entries missing the field part entirely.
			if not ("." in rest):
				notes.append("%s memory key '%s' has no field — dropped" % [where, ks])
				continue
		if nks != ks:
			changed = true
			notes.append("%s key: '%s' -> '%s'" % [where, ks, nks])
		fixed[nks] = req[k]
	if changed or fixed.size() != req.size():
		req.clear()
		for k2 in fixed.keys():
			req[k2] = fixed[k2]

# Keyword -> roster-name preference list, in order. First sheet that exists
# in the roster wins. Returns "" if no keyword matches.
static func _role_pick(text: String, sheets: Array) -> String:
	var rules: Array = [
		# Bandits/thugs/outlaws use the Hunter sheet (leather/rough),
		# closer to a bandit silhouette than the polished Knight armor.
		[["bandit","thug","outlaw","robber","brigand","raider","poacher","ranger","scout","tracker","archer","hunter"], ["Hunter"]],
		[["villain","warrior","fighter","guard","soldier","captain","knight","paladin"], ["Knight"]],
		[["elder","hermit","sage","old","wizard","mage","wise"], ["OldMan"]],
		[["monk","priest","cleric","acolyte","abbot","nun"], ["Monk"]],
		[["princess","queen","noble","lady","royal","duchess"], ["Princess"]],
		[["villager","peasant","farmer","merchant","trader","shopkeep","baker","commoner","child","kid"], ["Villager"]],
	]
	for r in rules:
		var keywords: Array = r[0]
		for kw in keywords:
			if String(kw) in text:
				for sheet in r[1]:
					if _has_ci(sheets, String(sheet)):
						return String(sheet)
	return ""

static func _has_ci(arr: Array, needle: String) -> bool:
	var n: String = needle.to_lower()
	for s in arr:
		if String(s).to_lower() == n:
			return true
	return false

# Pick the closest roster string by Levenshtein distance, biased to prefix
# match. Returns "" if no candidate is reasonable (distance > 6).
static func _nearest(s: String, arr: Array) -> String:
	var lo: String = s.to_lower()
	var best: String = ""
	var best_d: int = 999
	for c in arr:
		var cs: String = String(c)
		var cl: String = cs.to_lower()
		# perfect prefix containment wins immediately
		if cl.begins_with(lo) or lo.begins_with(cl):
			return cs
		var d: int = _lev(lo, cl)
		if d < best_d:
			best_d = d
			best = cs
	if best_d > 6:
		return ""
	return best

static func _lev(a: String, b: String) -> int:
	var n: int = a.length()
	var m: int = b.length()
	if n == 0: return m
	if m == 0: return n
	var prev: PackedInt32Array = PackedInt32Array()
	prev.resize(m + 1)
	for j in m + 1: prev[j] = j
	for i in range(1, n + 1):
		var cur: PackedInt32Array = PackedInt32Array()
		cur.resize(m + 1)
		cur[0] = i
		for j in range(1, m + 1):
			var cost: int = 0 if a[i-1] == b[j-1] else 1
			cur[j] = min(min(cur[j-1] + 1, prev[j] + 1), prev[j-1] + cost)
		prev = cur
	return prev[m]
