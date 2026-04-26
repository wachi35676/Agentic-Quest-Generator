class_name OllamaClient
extends Node

# Thin one-shot wrapper around POST http://localhost:11434/api/generate.
# Non-streaming for v1 (Ollama's stream=false returns the full text at once).
#
# Usage:
#   var c := OllamaClient.new()
#   add_child(c)
#   var resp = await c.generate("phi4", system_prompt, user_prompt)
#   if resp.ok: ... resp.text
#   else: ... resp.error

const DEFAULT_HOST := "http://localhost:11434"
const ENDPOINT := "/api/generate"

@export var host: String = DEFAULT_HOST
@export var timeout_sec: float = 180.0     # phi4 14B can be slow

signal progress(stage: String, elapsed: float)

var _http: HTTPRequest

func _ready() -> void:
	_http = HTTPRequest.new()
	_http.timeout = timeout_sec
	add_child(_http)

# Returns Dictionary: {ok: bool, text: String, error: String, raw: Dictionary}
func generate(model: String, system_prompt: String, user_prompt: String, options: Dictionary = {}, format: String = "") -> Dictionary:
	var url := host + ENDPOINT
	var body := {
		"model": model,
		"system": system_prompt,
		"prompt": user_prompt,
		"stream": false,
		"options": options,
		# Disable qwen3's <think> reasoning preamble — we don't want to wait
		# for hidden chain-of-thought before the JSON answer arrives.
		"think": false,
	}
	# When `format` is "json", Ollama constrains output to valid JSON via
	# grammar-based sampling. Required for small models like qwen3:4b that
	# otherwise emit reasoning prose despite explicit instructions.
	if format != "":
		body["format"] = format
	# Ask Ollama for low-randomness output for schema fidelity (caller can override).
	if not body.options.has("temperature"):
		# Higher temp for creative variety. Schema fidelity is enforced by
		# the sanitizer + repair loop, so we can afford to let qwen3
		# breathe. 0.3 was making it copy the fixture verbatim.
		body.options["temperature"] = 0.85
	if not body.options.has("num_ctx"):
		body.options["num_ctx"] = 8192    # quest prompt + example are ~3k tokens
	var headers := ["Content-Type: application/json"]
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
		return {"ok": false, "error": "transport result=%d (timeout? is `ollama serve` running on %s?)" % [rc, host]}
	if http_code < 200 or http_code >= 300:
		return {"ok": false, "error": "HTTP %d: %s" % [http_code, raw_body.get_string_from_utf8().substr(0, 400)]}
	var text := raw_body.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Dictionary):
		return {"ok": false, "error": "Ollama response is not JSON object"}
	var d: Dictionary = parsed
	return {"ok": true, "text": String(d.get("response","")), "raw": d}

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

# Helper: a hello-world to sanity-check connectivity. Doesn't validate JSON.
func ping(model: String = "phi4-mini") -> Dictionary:
	return await generate(model, "Reply with the single word: pong", "ping")
