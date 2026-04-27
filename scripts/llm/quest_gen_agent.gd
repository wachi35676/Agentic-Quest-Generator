class_name QuestGenAgent
extends Node

# Orchestrator: builds the prompt, calls Ollama, parses + validates, runs the
# repair loop, and emits the final bundle (or a failure reason).
#
# Phase tags emitted via `progress` (UI listens):
#   "calling"     — first model call in flight
#   "validating"  — response received, checking
#   "repairing"   — invalid; sending corrections back
#   "ready"       — bundle valid; spawner can take over
#   "failed"      — gave up after MAX_REPAIRS or transport died

signal progress(stage: String, detail: String)
signal result_ready(bundle: Dictionary)
signal failed(reason: String)

const MAX_REPAIRS := 6
const FALLBACK_FIXTURE := "res://tests/fixtures/heirloom_quest.json"

# Switched to Groq for fast LPU-backed inference. gpt-oss-120b is the
# preferred high-quality option but is project-blocked on the user's
# free tier — flip back once it's enabled in the Groq console.
# llama-3.3-70b-versatile is throttled at 12K TPM on the free tier,
# which our ~7K-token branching prompt blows past after two calls.
# llama-3.1-8b-instant has a much wider TPM ceiling and stays reliable.
# 70b accepts our ~7K-token branching prompt; 8b's per-request cap is
# 6K, which 413s on the full bundle.  8b handles the smaller schemas
# (expansion, simple-quest, continuation) where the prompt fits.
@export var model: String = "llama-3.3-70b-versatile"
@export var expand_model: String = "llama-3.1-8b-instant"

# Cache key = "<npc_name>|<parent_node>|<choice_id>" -> Dictionary node.
var _expand_cache: Dictionary = {}
# Same key -> Array of awaitable callables waiting on the inflight call.
# When a request is in flight, concurrent expand() calls await its
# completion signal instead of triggering duplicate generations.
var _inflight: Dictionary = {}

signal _expand_ready(key: String, node: Dictionary)

# Caller-supplied NPC names that exist in the world but not in the
# bundle's npcs[] (e.g. the hand-placed quest-giver). Forwarded to the
# validator so objectives may reference them without errors.
var _extra_known: Array = []

var _client: CompositeClient

func _ready() -> void:
	# Composite client tries Groq first (fast), falls back to Gemini
	# when Groq returns daily/per-minute quota errors. Keeps the game
	# playable past Groq's 100K-tokens/day shared-org cap.
	_client = CompositeClient.new()
	add_child(_client)
	_client.progress.connect(func(stage, elapsed):
		progress.emit(stage, "%.0fs" % elapsed))

# Async. Returns Dictionary {ok, bundle, error}.
func generate(premise: String) -> Dictionary:
	_extra_known = []
	var system := LlmPrompts.build_system_prompt()
	var user := premise.strip_edges()
	if user == "":
		user = LlmPrompts.DEFAULT_PREMISE
	print("[agent] starting generation with model=", model)
	progress.emit("calling", model)
	var resp := await _client.generate(model, system, user, {"num_predict": 4096})
	if not resp.ok:
		print("[agent] transport failure: ", resp.error)
		failed.emit(resp.error)
		return {"ok": false, "error": resp.error}

	var attempt := 0
	var last_text: String = resp.text
	print("[agent] initial response (%d chars). first 400: %s" % [last_text.length(), last_text.substr(0, 400)])
	_dump_raw(last_text, "initial")
	while true:
		progress.emit("validating", "attempt %d" % (attempt + 1))
		var parse := _parse_bundle(last_text)
		if not parse.ok:
			print("[agent] PARSE FAIL attempt=%d: %s" % [attempt, parse.error])
			print("[agent] raw response head: ", last_text.substr(0, 600))
			var parse_errs: Array = [parse.error]
			if attempt >= MAX_REPAIRS:
				print("[agent] giving up after %d parse failures, falling back" % attempt)
				failed.emit("parse failure after %d retries: %s" % [attempt, parse.error])
				return _fallback("parse_failure")
			progress.emit("repairing", "%d/%d" % [attempt + 1, MAX_REPAIRS])
			attempt += 1
			var repair_resp := await _client.generate(model, system,
					user + "\n\n" + LlmPrompts.build_repair_prompt(parse_errs),
					{"num_predict": 4096})
			if not repair_resp.ok:
				print("[agent] repair transport failed: ", repair_resp.error)
				failed.emit(repair_resp.error)
				return _fallback("transport_failure")
			last_text = repair_resp.text
			continue

		var bundle: Dictionary = parse.bundle
		var san: Dictionary = QuestSanitizer.sanitize(bundle, _extra_known)
		bundle = san.bundle
		var fixes: Array = san.notes
		if not fixes.is_empty():
			print("[agent] sanitizer applied %d fixes:" % fixes.size())
			for i in range(min(fixes.size(), 12)):
				print("  ~ ", fixes[i])
		var errs: Array = QuestValidator.validate(bundle, _extra_known)
		if errs.is_empty():
			print("[agent] VALID bundle on attempt %d. quest.id=%s, branches=%d, npcs=%d" % [attempt + 1,
					String(bundle.get("quest",{}).get("id","?")),
					(bundle.get("quest",{}).get("branches",[]) as Array).size(),
					(bundle.get("npcs",[]) as Array).size()])
			progress.emit("ready", "")
			result_ready.emit(bundle)
			return {"ok": true, "bundle": bundle}
		print("[agent] VALIDATION FAILED attempt=%d, %d errors:" % [attempt + 1, errs.size()])
		for i in range(min(errs.size(), 8)):
			print("  - ", errs[i])
		if attempt >= MAX_REPAIRS:
			print("[agent] giving up after %d validation failures, falling back" % (attempt + 1))
			failed.emit("validation failed %d times; first error: %s" % [attempt + 1, errs[0]])
			return _fallback("validation_failure")
		progress.emit("repairing", "%d/%d" % [attempt + 1, MAX_REPAIRS])
		attempt += 1
		var rresp := await _client.generate(model, system,
				user + "\n\n" + LlmPrompts.build_repair_prompt(errs),
				{"num_predict": 4096})
		if not rresp.ok:
			print("[agent] repair transport failed: ", rresp.error)
			failed.emit(rresp.error)
			return _fallback("transport_failure")
		last_text = rresp.text
		print("[agent] repair response (%d chars). first 400: %s" % [last_text.length(), last_text.substr(0, 400)])
		_dump_raw(last_text, "repair_%d" % attempt)
	# Unreachable.
	return {"ok": false, "error": "internal"}

# Tries hard to find JSON in the response. phi4 sometimes wraps with prose
# or fences despite the prompt; we strip what we can.
func _parse_bundle(text: String) -> Dictionary:
	var t := text.strip_edges()
	# strip ```json ... ``` fences
	if t.begins_with("```"):
		var nl := t.find("\n")
		if nl > 0:
			t = t.substr(nl + 1)
		if t.ends_with("```"):
			t = t.substr(0, t.length() - 3).strip_edges()
	# slice from first '{' to last '}'
	var first := t.find("{")
	var last := t.rfind("}")
	if first < 0 or last <= first:
		return {"ok": false, "error": "no JSON object found in response"}
	t = t.substr(first, last - first + 1)
	var parsed: Variant = JSON.parse_string(t)
	if not (parsed is Dictionary):
		return {"ok": false, "error": "JSON parse failed or root is not an object"}
	return {"ok": true, "bundle": parsed}

# Lazy expansion of one dialog node. Returns Dictionary {ok, node, error}.
# Caches by composite key so prefetched and on-demand calls converge.
func expand_node(ctx: Dictionary) -> Dictionary:
	var key := _expand_key(ctx)
	if _expand_cache.has(key):
		return {"ok": true, "node": _expand_cache[key], "cached": true}
	if _inflight.has(key):
		# Another caller is already running this expansion. Wait for the shared signal.
		var matched: Dictionary = await _wait_inflight(key)
		return {"ok": true, "node": matched, "shared": true}
	_inflight[key] = true
	var system := LlmPrompts.build_expand_system_prompt()
	var user := LlmPrompts.build_expand_user_prompt(ctx)
	progress.emit("expanding", key)
	var resp := await _client.generate(expand_model, system, user)
	if not resp.ok:
		_inflight.erase(key)
		var fallback_node := _fallback_node(ctx)
		_expand_cache[key] = fallback_node
		_expand_ready.emit(key, fallback_node)
		return {"ok": true, "node": fallback_node, "fallback": true, "error": resp.error}
	var parse := _parse_node(resp.text)
	if not parse.ok:
		_inflight.erase(key)
		var fb := _fallback_node(ctx)
		_expand_cache[key] = fb
		_expand_ready.emit(key, fb)
		return {"ok": true, "node": fb, "fallback": true, "error": parse.error}
	_expand_cache[key] = parse.node
	_inflight.erase(key)
	_expand_ready.emit(key, parse.node)
	return {"ok": true, "node": parse.node}

func _wait_inflight(key: String) -> Dictionary:
	while _inflight.has(key) and not _expand_cache.has(key):
		var args = await _expand_ready
		if String(args[0]) == key:
			return args[1]
	return _expand_cache.get(key, {"text":"...","choices":[]})

static func _expand_key(ctx: Dictionary) -> String:
	return "%s|%s|%s" % [
		String(ctx.get("npc_name","")),
		String(ctx.get("parent_node_id","")),
		String(ctx.get("choice_id","")),
	]

func _parse_node(text: String) -> Dictionary:
	var t := text.strip_edges()
	if t.begins_with("```"):
		var nl := t.find("\n")
		if nl > 0: t = t.substr(nl + 1)
		if t.ends_with("```"):
			t = t.substr(0, t.length() - 3).strip_edges()
	var first := t.find("{")
	var last := t.rfind("}")
	if first < 0 or last <= first:
		return {"ok": false, "error": "no JSON object in expand response"}
	t = t.substr(first, last - first + 1)
	var parsed: Variant = JSON.parse_string(t)
	if not (parsed is Dictionary):
		return {"ok": false, "error": "JSON parse failed"}
	var d: Dictionary = parsed
	if not d.has("text"):
		return {"ok": false, "error": "expand node missing 'text'"}
	if not d.has("choices"):
		d["choices"] = []
	# Same sanitation pass as full-bundle: strip non-ASCII from choice ids,
	# remove spaces from action verbs, fix predicate-key whitespace.
	for c in d.choices:
		if c is Dictionary:
			var ocid: String = String(c.get("id",""))
			var ncid: String = QuestSanitizer._ascii_id(ocid)
			if ncid != ocid and ncid != "":
				c["id"] = ncid
			var acts: Array = c.get("actions", [])
			for i in acts.size():
				acts[i] = QuestSanitizer._clean_action(String(acts[i]))
			QuestSanitizer._clean_predicates(c.get("requires", {}), [], "expand.choice")
	return {"ok": true, "node": d}

# Best-effort node when generation fails — keeps the dialog usable.
func _fallback_node(ctx: Dictionary) -> Dictionary:
	var hint: String = String(ctx.get("choice_hint",""))
	var text: String = "(...)" if hint == "" else hint
	return {"text": text, "choices": []}

# Simple-quest path: small schema, single objective, fast (5-15s).
# kind = LlmPrompts.SIMPLE_KIND_FETCH or SIMPLE_KIND_KILL.
# Returns Dictionary {ok, quest, error}. The quest dict has shape:
#   { id, title, description, objective:{type,params,required,description},
#     rewards:[{item_id,count}], dialog:{intro,active,complete} }
func generate_simple(npc_name: String, npc_role: String, kind: String, hint: String = "") -> Dictionary:
	var system := LlmPrompts.build_simple_system_prompt(kind)
	var user := LlmPrompts.build_simple_user_prompt(npc_role, npc_name, kind, hint)
	progress.emit("simple_quest", npc_name)
	# Use the small/fast model — schema is tiny, no need for 14B.
	# Pass format="json" so Ollama enforces strict JSON output via grammar
	# sampling. qwen3:4b ignores prose-level instructions to "output only
	# JSON" and dumps chain-of-thought instead; the format flag fixes that.
	# num_predict must be high enough to fit the full quest JSON — Ollama's
	# default of 128 truncates responses mid-object, leaving an unbalanced
	# brace count that the extractor can't parse.
	var opts := {"num_predict": 1024}
	var resp := await _client.generate(expand_model, system, user, opts, "json")
	if not resp.ok:
		return {"ok": false, "error": resp.error}
	_dump_raw(resp.text, "simple_%s_%s" % [npc_name.to_lower(), kind])
	print("[agent] simple raw (head 400): ", resp.text.substr(0, 400))
	var q: Variant = _extract_first_json(resp.text)
	if not (q is Dictionary):
		return {"ok": false, "error": "could not extract a JSON object from response"}
	var d: Dictionary = q
	if d.has("id"):
		d["id"] = QuestSanitizer._ascii_id(String(d["id"]))
	if not d.has("objective") or not d.has("title"):
		return {"ok": false, "error": "missing required fields (objective/title)"}
	return {"ok": true, "quest": d}

# Branching dynamic quest: full bundle (quest + branches + dialog tree +
# spawned NPCs/items) tailored to a hand-placed quest-giver. Uses the
# main 14B model + sanitizer + repair loop, same as the original
# generate() — just with a stronger system prompt encouraging
# action-driven branching.
func generate_branching(quest_giver_name: String, quest_giver_role: String) -> Dictionary:
	_extra_known = [quest_giver_name]
	var system := LlmPrompts.build_branching_system_prompt(quest_giver_name, quest_giver_role)
	var user := "Quest-giver: %s (role %s). Build the dynamic branching quest now. Single JSON object." % [
			quest_giver_name, quest_giver_role]
	print("[agent] starting branching generation for ", quest_giver_name)
	progress.emit("calling", model)
	var t0 := Time.get_ticks_msec()
	var resp := await _client.generate(model, system, user, {"num_predict": 4096})
	if not resp.ok:
		EvaluationLogger.log("quest_generated", "QuestGenAgent", {
			"phase": "branching", "parsed_ok": false, "transport_failed": true,
			"error": resp.error, "model": model, "elapsed_ms": Time.get_ticks_msec() - t0,
		})
		return {"ok": false, "error": resp.error}
	var attempt := 0
	var last_text: String = resp.text
	_dump_raw(last_text, "branching_initial")
	while true:
		var parse := _parse_bundle(last_text)
		if not parse.ok:
			if attempt >= MAX_REPAIRS:
				EvaluationLogger.log("quest_generated", "QuestGenAgent", {
					"phase": "branching", "parsed_ok": false, "attempt": attempt + 1,
					"error": parse.error, "model": model,
					"elapsed_ms": Time.get_ticks_msec() - t0,
				})
				return {"ok": false, "error": parse.error}
			attempt += 1
			progress.emit("repairing", "%d/%d" % [attempt, MAX_REPAIRS])
			var rr := await _client.generate(model, system,
					user + "\n\n" + LlmPrompts.build_repair_prompt([parse.error]),
					{"num_predict": 4096})
			if not rr.ok: return {"ok": false, "error": rr.error}
			last_text = rr.text
			_dump_raw(last_text, "branching_repair_%d" % attempt)
			continue
		var bundle: Dictionary = parse.bundle
		var san: Dictionary = QuestSanitizer.sanitize(bundle, _extra_known)
		bundle = san.bundle
		if not san.notes.is_empty():
			print("[agent] branching sanitizer: %d fixes" % san.notes.size())
		var errs: Array = QuestValidator.validate(bundle, _extra_known)
		if errs.is_empty():
			print("[agent] branching VALID on attempt %d" % (attempt + 1))
			progress.emit("ready", "")
			EvaluationLogger.log("quest_generated", "QuestGenAgent", {
				"phase": "branching", "parsed_ok": true, "schema_valid": true,
				"sanitizer_fix_count": san.notes.size(),
				"attempt": attempt + 1,
				"quest_id": String(bundle.get("quest", {}).get("id","")),
				"npc_count": (bundle.get("npcs", []) as Array).size(),
				"branch_count": (bundle.get("quest", {}).get("branches", []) as Array).size(),
				"model": model, "elapsed_ms": Time.get_ticks_msec() - t0,
				"raw_text_len": last_text.length(),
			})
			return {"ok": true, "bundle": bundle}
		print("[agent] branching validate failed (%d errors)" % errs.size())
		for i in range(min(errs.size(), 6)): print("  - ", errs[i])
		if attempt >= MAX_REPAIRS:
			EvaluationLogger.log("quest_generated", "QuestGenAgent", {
				"phase": "branching", "parsed_ok": true, "schema_valid": false,
				"sanitizer_fix_count": san.notes.size(),
				"attempt": attempt + 1,
				"validation_errors": errs,
				"model": model, "elapsed_ms": Time.get_ticks_msec() - t0,
			})
			return {"ok": false, "error": "validation failed: %s" % errs[0]}
		attempt += 1
		progress.emit("repairing", "%d/%d" % [attempt, MAX_REPAIRS])
		var rr2 := await _client.generate(model, system,
				user + "\n\n" + LlmPrompts.build_repair_prompt(errs),
				{"num_predict": 4096})
		if not rr2.ok: return {"ok": false, "error": rr2.error}
		last_text = rr2.text
		_dump_raw(last_text, "branching_repair_%d" % attempt)
	return {"ok": false, "error": "internal"}

# Wanderer-orchestrator call: reads action_ledger, returns either a
# continuation (full new quest bundle) or a closing (rewards + dialog).
# Returns Dictionary {ok, decision, wanderer_dialog, new_quest?, rewards?, error}.
func generate_orchestration(prev_quest_summary: Dictionary, ledger: Array,
		current_npc_names: Array, quest_giver_name: String,
		max_remaining: int) -> Dictionary:
	_extra_known = current_npc_names.duplicate()
	if not (quest_giver_name in _extra_known):
		_extra_known.append(quest_giver_name)
	var system := LlmPrompts.build_orchestration_system_prompt(
			quest_giver_name, current_npc_names, max_remaining)
	var user := LlmPrompts.build_orchestration_user_prompt(prev_quest_summary, ledger)
	progress.emit("orchestrating", quest_giver_name)
	var t0 := Time.get_ticks_msec()
	var resp := await _client.generate(model, system, user, {"num_predict": 4096}, "json")
	if not resp.ok:
		EvaluationLogger.log("orchestration_failed", "QuestGenAgent", {
			"phase": "orchestration", "transport_failed": true,
			"error": resp.error, "model": model,
			"elapsed_ms": Time.get_ticks_msec() - t0,
		})
		return {"ok": false, "error": resp.error}
	_dump_raw(resp.text, "orchestration")
	var p: Variant = _extract_first_json(resp.text)
	if not (p is Dictionary):
		return {"ok": false, "error": "could not extract JSON"}
	var d: Dictionary = p
	var decision: String = String(d.get("decision","")).to_lower()
	if decision != "continue" and decision != "complete":
		return {"ok": false, "error": "decision must be 'continue' or 'complete' (got '%s')" % decision}
	var dialog_str: String = String(d.get("wanderer_dialog",""))
	if dialog_str.strip_edges() == "":
		dialog_str = ("Words won't come tonight." if decision == "continue"
				else "It is finished, traveler.")
	var out: Dictionary = {"ok": true, "decision": decision, "wanderer_dialog": dialog_str}
	if decision == "continue":
		var new_quest: Variant = d.get("new_quest", null)
		if not (new_quest is Dictionary):
			return {"ok": false, "error": "decision=continue but new_quest missing"}
		var nq: Dictionary = new_quest
		# Sanitize + validate the embedded bundle. Pass extra_known so
		# objectives may reference the Wanderer (already exists) without
		# being dropped by the validator.
		var san: Dictionary = QuestSanitizer.sanitize(nq, _extra_known)
		nq = san.bundle
		if not san.notes.is_empty():
			print("[agent] orchestration sanitizer: %d fixes" % san.notes.size())
		# Hard rule: continuation MUST include at least one new NPC the
		# player can interact with. Empty npcs[] leaves nothing for the
		# player to do beyond re-talking to surviving NPCs.
		var fresh_npcs: Array = nq.get("npcs", [])
		if fresh_npcs.is_empty():
			print("[agent] orchestration rejected: continuation new_quest has no fresh NPCs")
			return {"ok": false, "error": "continuation must spawn at least 1 fresh NPC"}
		var errs: Array = QuestValidator.validate(nq, _extra_known)
		if not errs.is_empty():
			print("[agent] orchestration validation failed (%d errs); first: %s" % [errs.size(), errs[0]])
			return {"ok": false, "error": "validation: %s" % errs[0]}
		out["new_quest"] = nq
	else:
		var rewards: Variant = d.get("rewards", [])
		if not (rewards is Array):
			rewards = []
		out["rewards"] = rewards
	print("[agent] orchestration VALID (decision=%s)" % decision)
	# Verify memory claims (Option A): each claim must subset-match a
	# ledger entry of the same kind. Emit one event per claim so the
	# Python evaluator can compute Memory Consistency.
	var claims: Array = []
	if d.has("memory_claims") and (d.memory_claims is Array):
		claims = d.memory_claims
	for c in claims:
		if not (c is Dictionary): continue
		var ok_claim := _verify_memory_claim(c, ledger)
		EvaluationLogger.log("memory_claim", "QuestGenAgent", {
			"claim": c, "verified": ok_claim,
		})
	EvaluationLogger.log("quest_revised" if decision == "continue" else "orchestration_complete",
			"QuestGenAgent", {
		"decision": decision,
		"prev_quest_id": String(prev_quest_summary.get("id","")),
		"new_quest_id": String((out.get("new_quest", {}) as Dictionary).get("quest", {}).get("id","")) if decision == "continue" else "",
		"wanderer_dialog_len": dialog_str.length(),
		"memory_claim_count": claims.size(),
		"model": model, "elapsed_ms": Time.get_ticks_msec() - t0,
	})
	return out

# Subset-match a memory claim against the action ledger. A claim is valid
# iff some ledger entry has the same `kind` AND every key in the claim's
# `params` matches the ledger entry's params exactly.
func _verify_memory_claim(claim: Dictionary, ledger: Array) -> bool:
	var ck: String = String(claim.get("kind",""))
	var cp: Dictionary = claim.get("params", {})
	for entry in ledger:
		if not (entry is Dictionary): continue
		if String(entry.get("kind","")) != ck: continue
		var ep: Dictionary = (entry as Dictionary).get("params", {})
		var all_match := true
		for k in cp.keys():
			if String(ep.get(k, "")) != String(cp[k]):
				all_match = false
				break
		if all_match:
			return true
	return false

# Mid-quest continuation: small JSON pack of new_branches + dialog_patches
# tied to a milestone event. Called by main._on_milestone after the engine
# fires npc_killed / npc_give. Uses the fast model since the schema is
# small. 1 attempt + up to 2 repair retries (less aggressive than the big
# bundle to keep mid-action latency low).
func generate_continuation(quest_summary: Dictionary, quest_giver_name: String,
		current_npc_names: Array, event_kind: String, event_payload: Dictionary) -> Dictionary:
	_extra_known = current_npc_names.duplicate()
	if not (quest_giver_name in _extra_known):
		_extra_known.append(quest_giver_name)
	var system := LlmPrompts.build_continuation_system_prompt(quest_giver_name, current_npc_names)
	var user := LlmPrompts.build_continuation_user_prompt(quest_summary, event_kind, event_payload)
	progress.emit("continuation", event_kind)
	var opts := {"num_predict": 1024}
	var attempt := 0
	var last_text := ""
	while attempt <= 2:
		var resp: Dictionary
		if attempt == 0:
			resp = await _client.generate(expand_model, system, user, opts, "json")
		else:
			progress.emit("repairing-cont", "%d/2" % attempt)
			resp = await _client.generate(expand_model, system,
					user + "\n\n" + LlmPrompts.build_repair_prompt([_last_cont_err]),
					opts, "json")
		if not resp.ok:
			return {"ok": false, "error": resp.error}
		last_text = resp.text
		_dump_raw(last_text, "continuation_%s_%d" % [event_kind, attempt])
		var p: Variant = _extract_first_json(last_text)
		if not (p is Dictionary):
			_last_cont_err = "could not extract JSON object"
			attempt += 1
			continue
		var pack: Dictionary = p
		var san: Dictionary = QuestSanitizer.sanitize_continuation(pack, current_npc_names + [quest_giver_name])
		pack = san.bundle
		if not san.notes.is_empty():
			print("[agent] continuation sanitizer: %d fixes" % san.notes.size())
		var errs: Array = QuestValidator.validate_continuation(pack, current_npc_names + [quest_giver_name])
		if errs.is_empty():
			print("[agent] continuation VALID on attempt %d (kind=%s)" % [attempt + 1, event_kind])
			return {"ok": true, "pack": pack}
		print("[agent] continuation validate failed (%d errors)" % errs.size())
		for i in range(min(errs.size(), 4)): print("  - ", errs[i])
		_last_cont_err = String(errs[0])
		attempt += 1
	return {"ok": false, "error": "validation failed: " + _last_cont_err}

var _last_cont_err: String = ""

# Two-stage quest, stage 1: fetch with extra "this is half a story" framing.
func generate_stage1(npc_name: String, npc_role: String) -> Dictionary:
	var system := LlmPrompts.build_stage1_system_prompt()
	var user := LlmPrompts.build_simple_user_prompt(npc_role, npc_name,
			LlmPrompts.SIMPLE_KIND_FETCH, "stage 1 of a two-part quest")
	progress.emit("stage1", npc_name)
	var resp := await _client.generate(expand_model, system, user, {"num_predict": 1024}, "json")
	if not resp.ok: return {"ok": false, "error": resp.error}
	_dump_raw(resp.text, "stage1_%s" % npc_name.to_lower())
	var q: Variant = _extract_first_json(resp.text)
	if not (q is Dictionary):
		return {"ok": false, "error": "could not extract JSON"}
	var d: Dictionary = q
	if d.has("id"): d["id"] = QuestSanitizer._ascii_id(String(d["id"]))
	if not d.has("objective") or not d.has("title"):
		return {"ok": false, "error": "missing required fields"}
	return {"ok": true, "quest": d}

# Stage 2: generated AFTER the player picks a path. `stage1_summary` is a
# one-line description of what they did. `path` is honor|greed.
func generate_stage2(npc_name: String, npc_role: String, stage1_summary: String, path: String) -> Dictionary:
	var system := LlmPrompts.build_stage2_system_prompt(stage1_summary, path)
	var kind: String = LlmPrompts.SIMPLE_KIND_KILL if path == LlmPrompts.TWO_STAGE_PATH_A else LlmPrompts.SIMPLE_KIND_FETCH
	var user := LlmPrompts.build_simple_user_prompt(npc_role, npc_name, kind,
			"stage 2 — player chose %s" % path)
	progress.emit("stage2", "%s/%s" % [npc_name, path])
	var resp := await _client.generate(expand_model, system, user, {"num_predict": 1024}, "json")
	if not resp.ok: return {"ok": false, "error": resp.error}
	_dump_raw(resp.text, "stage2_%s_%s" % [npc_name.to_lower(), path])
	var q: Variant = _extract_first_json(resp.text)
	if not (q is Dictionary):
		return {"ok": false, "error": "could not extract JSON"}
	var d: Dictionary = q
	if d.has("id"): d["id"] = QuestSanitizer._ascii_id(String(d["id"]))
	if not d.has("objective") or not d.has("title"):
		return {"ok": false, "error": "missing required fields"}
	return {"ok": true, "quest": d}

# Robust JSON object extractor: skips text/markdown/<think> noise, finds
# the first balanced {...} via brace counting (string-aware), parses it.
# Returns the parsed Variant on success or null on failure.
static func _extract_first_json(text: String) -> Variant:
	var t: String = text
	# Strip <think>...</think> blocks (qwen3's reasoning preamble).
	var ti := t.find("<think>")
	while ti >= 0:
		var te := t.find("</think>", ti)
		if te < 0: break
		t = t.substr(0, ti) + t.substr(te + 8)
		ti = t.find("<think>")
	# Walk for the first balanced object, ignoring braces inside strings.
	var depth: int = 0
	var start: int = -1
	var in_str: bool = false
	var esc: bool = false
	var i: int = 0
	while i < t.length():
		var ch: String = t[i]
		if in_str:
			if esc: esc = false
			elif ch == "\\": esc = true
			elif ch == "\"": in_str = false
		else:
			if ch == "\"":
				in_str = true
			elif ch == "{":
				if depth == 0: start = i
				depth += 1
			elif ch == "}":
				depth -= 1
				if depth == 0 and start >= 0:
					var slice: String = t.substr(start, i - start + 1)
					var parsed: Variant = JSON.parse_string(slice)
					if parsed is Dictionary:
						return parsed
					# Unbalanced or invalid — keep scanning for the next one.
					start = -1
		i += 1
	return null

# Dump raw model output to user://llm_debug/<tag>.txt for offline iteration.
# user:// resolves to %APPDATA%/Godot/app_userdata/<project>/.
func _dump_raw(text: String, tag: String) -> void:
	var dir := DirAccess.open("user://")
	if dir == null: return
	if not dir.dir_exists("llm_debug"):
		dir.make_dir("llm_debug")
	var f := FileAccess.open("user://llm_debug/%s.txt" % tag, FileAccess.WRITE)
	if f == null: return
	f.store_string(text)
	f.close()

func _fallback(reason: String) -> Dictionary:
	# Load the gold-standard fixture so the player still gets a quest.
	var f := FileAccess.open(FALLBACK_FIXTURE, FileAccess.READ)
	if f == null:
		return {"ok": false, "error": reason}
	var bundle: Variant = JSON.parse_string(f.get_as_text())
	f.close()
	if not (bundle is Dictionary):
		return {"ok": false, "error": reason}
	progress.emit("ready", "fallback fixture")
	result_ready.emit(bundle)
	return {"ok": true, "bundle": bundle, "fallback": true, "reason": reason}
