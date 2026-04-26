class_name QuestSanitizer
extends RefCounted

# Deterministic cleanup of common qwen3:14b output quirks before validation.
# Each pass returns the (possibly mutated) bundle plus a list of fix notes
# that we log so we can see what the model actually emitted vs what we
# coerced it into. The validator runs AFTER this — anything still wrong
# falls into the repair loop as a real prompt error.

static func sanitize(bundle: Variant) -> Dictionary:
	var notes: Array = []
	if not (bundle is Dictionary):
		return {"bundle": bundle, "notes": notes}
	var b: Dictionary = bundle
	_clean_quest(b.get("quest", {}), notes)
	for npc in b.get("npcs", []):
		_clean_npc(npc, notes)
	return {"bundle": b, "notes": notes}

# ---- quest-level ----
static func _clean_quest(q: Dictionary, notes: Array) -> void:
	if q.is_empty(): return
	var oid: String = String(q.get("id",""))
	var nid: String = _ascii_id(oid)
	if nid != oid:
		notes.append("quest.id: '%s' -> '%s'" % [oid, nid])
		q["id"] = nid
	for b in q.get("branches", []):
		var obid: String = String(b.get("id",""))
		var nbid: String = _ascii_id(obid)
		if nbid != obid:
			notes.append("branch.id: '%s' -> '%s'" % [obid, nbid])
			b["id"] = nbid
		_clean_predicates(b.get("requires_flags", {}), notes, "branch.requires_flags")
		for o in b.get("objectives", []):
			_clean_objective(o, notes)
	for o in q.get("objectives", []):
		_clean_objective(o, notes)
	for o in q.get("fail_conditions", []):
		_clean_objective(o, notes)

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
			# actions
			var acts: Array = c.get("actions", [])
			for i in acts.size():
				var a: String = String(acts[i])
				var ca: String = _clean_action(a)
				if ca != a:
					notes.append("action: '%s' -> '%s'" % [a, ca])
					acts[i] = ca
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

# Removes whitespace inside an action string and around the colon.
# Examples: "give_ player:gem_red" -> "give_player:gem_red"
#           "set_flag :foo=true"   -> "set_flag:foo=true"
static func _clean_action(a: String) -> String:
	var s: String = a.strip_edges()
	# drop ALL spaces — verbs, args, and keys never legitimately contain them
	s = s.replace(" ", "")
	s = s.replace("\t", "")
	return s

static func _clean_predicates(req: Dictionary, notes: Array, where: String) -> void:
	# Drop spaces in keys (e.g. "flag : persuaded" -> "flag:persuaded").
	var fixed: Dictionary = {}
	var changed := false
	for k in req.keys():
		var ks: String = String(k)
		var nks: String = ks.replace(" ", "").replace("\t", "")
		if nks != ks:
			changed = true
			notes.append("%s key: '%s' -> '%s'" % [where, ks, nks])
		fixed[nks] = req[k]
	if changed:
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
