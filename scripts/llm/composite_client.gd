class_name CompositeClient
extends Node

# Multi-provider wrapper. Tries Groq first (fast LPU); when Groq returns
# 429 / quota errors, falls through to Gemini (separate quota pool) so
# generation keeps working past Groq's daily TPD cap.
#
# Same generate(model, system, user, options, format) -> {ok, text, error}
# signature as the individual clients so QuestGenAgent doesn't change.
#
# `model` here can be either a Groq model id or a Gemini model id; the
# wrapper picks the right backend by checking which provider knows the
# name. Falls back to Gemini's flash if Groq's named model fails.

signal progress(stage: String, elapsed: float)

const GROQ_MODELS := [
	"llama-3.3-70b-versatile",
	"llama-3.1-8b-instant",
	"openai/gpt-oss-120b",
	"openai/gpt-oss-20b",
	"moonshotai/kimi-k2-instruct",
]
# Gemini model used when Groq is exhausted.
const GEMINI_FALLBACK_MODEL := "gemini-2.5-flash"

var _groq: GroqClient
var _gemini: GeminiClient
# Once Groq has returned a quota error in this session, suppress retries
# against it until we hit a cooldown window. Avoids spending half a
# second per call hitting Groq just to be 429'd.
var _groq_blocked_until_ms: int = 0
const GROQ_COOLDOWN_MS := 5 * 60 * 1000   # 5 min

func _ready() -> void:
	_groq = GroqClient.new()
	add_child(_groq)
	_gemini = GeminiClient.new()
	add_child(_gemini)
	_groq.progress.connect(func(s, e): progress.emit(s, e))
	_gemini.progress.connect(func(s, e): progress.emit(s, e))

func generate(model: String, system_prompt: String, user_prompt: String,
		options: Dictionary = {}, format: String = "") -> Dictionary:
	var prefer_groq: bool = model in GROQ_MODELS
	var groq_available: bool = Time.get_ticks_msec() >= _groq_blocked_until_ms
	if prefer_groq and groq_available:
		var r: Dictionary = await _groq.generate(model, system_prompt, user_prompt, options, format)
		if r.get("ok", false):
			return r
		# Groq failed — if it looks like a quota issue, mark Groq blocked
		# and fall through to Gemini. Other errors (parse, transport) are
		# returned as-is.
		var err: String = String(r.get("error",""))
		if _is_groq_quota_error(err):
			_groq_blocked_until_ms = Time.get_ticks_msec() + GROQ_COOLDOWN_MS
			print("[composite] Groq quota exhausted, switching to Gemini for the next 5min")
			progress.emit("Groq exhausted; using Gemini", 0.0)
		else:
			return r
	# Fallback path: Gemini.
	return await _gemini.generate(GEMINI_FALLBACK_MODEL, system_prompt, user_prompt, options, format)

static func _is_groq_quota_error(err: String) -> bool:
	# Look for HTTP 429 OR daily/per-minute quota markers.
	if err.find("HTTP 429") >= 0: return true
	if err.find("rate_limit_exceeded") >= 0: return true
	if err.find("tokens per day") >= 0: return true
	if err.find("tokens per minute") >= 0: return true
	if err.find("Rate limit reached") >= 0: return true
	return false
