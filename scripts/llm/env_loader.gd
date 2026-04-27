class_name EnvLoader
extends RefCounted

# Tiny .env reader. Loads the project's .env file once and caches the
# key/value pairs in a static dict. Used to pull GEMINI_API_KEY without
# baking secrets into source.

static var _cache: Dictionary = {}
static var _loaded: bool = false

static func get_var(key: String, fallback: String = "") -> String:
	_ensure_loaded()
	return String(_cache.get(key, fallback))

# Returns every value matching `prefix*`, in numeric-suffix order. Used to
# load multiple API keys (GROQ_API_KEY, GROQ_API_KEY2, GROQ_API_KEY3, ...)
# so the client can rotate when one hits a rate limit.
static func get_keys_with_prefix(prefix: String) -> Array:
	_ensure_loaded()
	var matches: Array = []
	for k in _cache.keys():
		var ks: String = String(k)
		if ks == prefix or (ks.begins_with(prefix) and ks.length() > prefix.length()):
			matches.append(ks)
	# Sort: bare prefix first, then numerically by suffix.
	matches.sort_custom(func(a, b):
		if a == prefix: return true
		if b == prefix: return false
		return a < b)
	var out: Array = []
	for k in matches:
		var v: String = String(_cache[k])
		if v != "": out.append(v)
	return out

static func _ensure_loaded() -> void:
	if _loaded:
		return
	_loaded = true
	# Try res://.env (project root); fall back to user:// for exports.
	for path in ["res://.env", "user://.env"]:
		if FileAccess.file_exists(path):
			_parse(path)
			return
	push_warning("EnvLoader: no .env file found in project root")

static func _parse(path: String) -> void:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return
	while not f.eof_reached():
		var line: String = f.get_line().strip_edges()
		if line == "" or line.begins_with("#"):
			continue
		var eq: int = line.find("=")
		if eq <= 0:
			continue
		var k: String = line.substr(0, eq).strip_edges()
		var v: String = line.substr(eq + 1).strip_edges()
		# Strip surrounding quotes if present.
		if v.length() >= 2 and ((v.begins_with("\"") and v.ends_with("\"")) \
				or (v.begins_with("'") and v.ends_with("'"))):
			v = v.substr(1, v.length() - 2)
		_cache[k] = v
	f.close()
