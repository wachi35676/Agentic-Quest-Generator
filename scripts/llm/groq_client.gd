class_name GroqClient
extends Node

# OpenAI-compatible Groq client. Drop-in replacement for GeminiClient
# matching the same generate(model, system, user, options, format) -> {ok,
# text, error} signature so QuestGenAgent doesn't need to change.
#
#   POST https://api.groq.com/openai/v1/chat/completions
#   Header: Authorization: Bearer <GROQ_API_KEY>
#   Body:  { model, messages, max_completion_tokens, temperature,
#            response_format: {type: "json_object"} }
#   Response: choices[0].message.content
#
# API key pulled from project .env (GROQ_API_KEY).

const HOST := "https://api.groq.com"
const ENDPOINT := "/openai/v1/chat/completions"

@export var timeout_sec: float = 60.0

signal progress(stage: String, elapsed: float)

var _http: HTTPRequest
# Pool of GROQ_API_KEY* values from .env. We rotate to the next key on
# 429s so a TPM/RPM exhaustion on one key doesn't block the player —
# they get to keep generating quests as long as ANY key has headroom.
var _keys: Array = []
var _key_idx: int = 0

func _ready() -> void:
	_http = HTTPRequest.new()
	_http.timeout = timeout_sec
	add_child(_http)
	_keys = EnvLoader.get_keys_with_prefix("GROQ_API_KEY")
	if _keys.is_empty():
		push_warning("GroqClient: no GROQ_API_KEY* found in .env")
	else:
		print("[groq] loaded %d API key(s)" % _keys.size())

# Returns Dictionary {ok, text, error, raw}.
# `options` recognised keys:
#   temperature   -> temperature
#   num_predict   -> max_completion_tokens   (legacy Ollama name kept for compat)
#   max_tokens    -> max_completion_tokens
# `format` == "json" -> response_format: { type: "json_object" }
func generate(model: String, system_prompt: String, user_prompt: String,
		options: Dictionary = {}, format: String = "") -> Dictionary:
	if _keys.is_empty():
		return {"ok": false, "error": "no GROQ_API_KEY* configured in .env"}

	var body: Dictionary = {
		"model": model,
		"messages": [
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
		],
		"temperature": options.get("temperature", 1.0),
	}
	var max_out: int = int(options.get("num_predict", options.get("max_tokens", 0)))
	if max_out > 0:
		body["max_completion_tokens"] = max_out
	if format == "json":
		body["response_format"] = {"type": "json_object"}

	var url: String = HOST + ENDPOINT

	# Retry policy:
	#   - 429 → first try rotating to the next key (TPM/RPM is per-key)
	#   - If we've burned through every key and still 429 → wait the
	#     server-suggested seconds and retry once more
	# Total attempt cap = key_count + 1.
	var rotated_count: int = 0
	var max_rotations: int = _keys.size()
	while true:
		var key_str: String = String(_keys[_key_idx])
		var headers := [
			"Content-Type: application/json",
			"Authorization: Bearer " + key_str,
		]
		var start := Time.get_ticks_msec()
		progress.emit("calling " + model + " (key %d/%d)" % [_key_idx + 1, _keys.size()], 0.0)
		var err := _http.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
		if err != OK:
			return {"ok": false, "error": "HTTPRequest.request returned %d" % err}
		var ticker := _start_progress_ticker(model, start)
		var result: Array = await _http.request_completed
		if ticker != null:
			ticker.stop()
			ticker.queue_free()
		var rc: int = result[0]
		var http_code: int = result[1]
		var raw_body: PackedByteArray = result[3]
		if rc != HTTPRequest.RESULT_SUCCESS:
			return {"ok": false, "error": "transport result=%d" % rc}
		var text := raw_body.get_string_from_utf8()
		if http_code == 429:
			if rotated_count < max_rotations - 1:
				# Try the next key — TPM/RPM is per-key on Groq.
				rotated_count += 1
				_key_idx = (_key_idx + 1) % _keys.size()
				progress.emit("rate-limited; rotating to key %d/%d" % [_key_idx + 1, _keys.size()], 0.0)
				continue
			# All keys 429. Don't wait — let CompositeClient detect the
			# error and fall through to Gemini. Waiting 20s for an
			# org-wide daily cap to reset is hopeless anyway.
		if http_code < 200 or http_code >= 300:
			return {"ok": false, "error": "HTTP %d: %s" % [http_code, text.substr(0, 600)]}
		return _parse_success(text)
	return {"ok": false, "error": "unreachable"}

func _parse_success(text: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Dictionary):
		return {"ok": false, "error": "Groq response is not JSON object"}
	var d: Dictionary = parsed
	var choices: Array = d.get("choices", [])
	if choices.is_empty():
		return {"ok": false, "error": "no choices in Groq response", "raw": d}
	var msg: Dictionary = (choices[0] as Dictionary).get("message", {})
	var content: String = String(msg.get("content", ""))
	return {"ok": true, "text": content, "raw": d}

# Pulls "try again in 12.34s" out of Groq's 429 error body.
static func _parse_retry_seconds(body: String) -> float:
	var rx := RegEx.new()
	rx.compile(r"try again in ([\d\.]+)s")
	var m := rx.search(body)
	if m == null: return 5.0
	return float(m.get_string(1))

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
