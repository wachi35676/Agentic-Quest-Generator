class_name GeminiClient
extends Node

# Drop-in replacement for OllamaClient using the Gemini REST API.
# https://ai.google.dev/gemini-api/docs/text-generation
#
#   POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
#   Header: x-goog-api-key: <GEMINI_API_KEY>
#   Body:   {system_instruction, contents, generationConfig}
#   Response: candidates[0].content.parts[0].text
#
# API key pulled from project .env via EnvLoader (GEMINI_API_KEY).
# Same `generate(model, system, user, options, format) -> {ok, text, error}`
# signature as OllamaClient so QuestGenAgent doesn't change.

const HOST := "https://generativelanguage.googleapis.com"
const ENDPOINT := "/v1beta/models/%s:generateContent"

@export var timeout_sec: float = 60.0

signal progress(stage: String, elapsed: float)

var _http: HTTPRequest

func _ready() -> void:
	_http = HTTPRequest.new()
	_http.timeout = timeout_sec
	add_child(_http)

# Returns Dictionary {ok, text, error, raw}.
# `options` recognised keys (mapped to Gemini's generationConfig):
#   temperature   -> temperature
#   num_predict   -> maxOutputTokens   (kept name for OllamaClient compat)
#   max_tokens    -> maxOutputTokens
# `format` == "json" -> responseMimeType: application/json
func generate(model: String, system_prompt: String, user_prompt: String,
		options: Dictionary = {}, format: String = "") -> Dictionary:
	var key := EnvLoader.get_var("GEMINI_API_KEY", "")
	if key == "":
		return {"ok": false, "error": "GEMINI_API_KEY not set in .env"}

	var gen_cfg: Dictionary = {}
	if options.has("temperature"):
		gen_cfg["temperature"] = options["temperature"]
	else:
		# Gemini-3 docs: "strongly recommend keeping temperature at 1.0";
		# lower values can cause looping / degraded reasoning.
		gen_cfg["temperature"] = 1.0
	var max_out: int = int(options.get("num_predict", options.get("max_tokens", 0)))
	if max_out > 0:
		gen_cfg["maxOutputTokens"] = max_out
	if format == "json":
		gen_cfg["responseMimeType"] = "application/json"
	# thinkingConfig is supported only on gemini-3+ models. 2.5-flash
	# rejects it (HTTP 400 INVALID_ARGUMENT). Emit only for gemini-3 IDs.
	if model.begins_with("gemini-3"):
		gen_cfg["thinkingConfig"] = {"thinkingLevel": "low"}

	var body := {
		"system_instruction": {"parts": [{"text": system_prompt}]},
		"contents": [{"parts": [{"text": user_prompt}]}],
		"generationConfig": gen_cfg,
	}

	var url: String = HOST + (ENDPOINT % model)
	var headers := [
		"Content-Type: application/json",
		"x-goog-api-key: " + key,
	]

	var start := Time.get_ticks_msec()
	progress.emit("calling " + model, 0.0)
	var err := _http.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		return {"ok": false, "error": "HTTPRequest.request returned %d" % err}
	var ticker := _start_progress_ticker(model, start)
	var result: Array = await _http.request_completed
	if ticker != null:
		ticker.stop()
		ticker.queue_free()
	# result = [result_code, response_code, headers, body]
	var rc: int = result[0]
	var http_code: int = result[1]
	var raw_body: PackedByteArray = result[3]
	if rc != HTTPRequest.RESULT_SUCCESS:
		return {"ok": false, "error": "transport result=%d (timeout? offline?)" % rc}
	var text := raw_body.get_string_from_utf8()
	if http_code < 200 or http_code >= 300:
		return {"ok": false, "error": "HTTP %d: %s" % [http_code, text.substr(0, 600)]}
	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Dictionary):
		return {"ok": false, "error": "Gemini response is not JSON object"}
	var d: Dictionary = parsed
	# Pull candidates[0].content.parts[0].text
	var cands: Array = d.get("candidates", [])
	if cands.is_empty():
		# Probably blocked by safety filters or quota.
		var fr: String = String(d.get("promptFeedback", {}).get("blockReason", ""))
		return {"ok": false, "error": "no candidates (blockReason=%s)" % fr, "raw": d}
	var c0: Dictionary = cands[0]
	var content: Dictionary = c0.get("content", {})
	var parts: Array = content.get("parts", [])
	if parts.is_empty():
		return {"ok": false, "error": "candidate has no parts", "raw": d}
	var out_text := ""
	for p in parts:
		out_text += String((p as Dictionary).get("text", ""))
	return {"ok": true, "text": out_text, "raw": d}

func _start_progress_ticker(model: String, start_ms: int) -> Timer:
	var t := Timer.new()
	t.wait_time = 1.0
	t.one_shot = false
	add_child(t)
	t.timeout.connect(func():
		var elapsed := (Time.get_ticks_msec() - start_ms) / 1000.0
		progress.emit("calling %s" % model, elapsed)
	)
	t.start()
	return t
