extends Node

# Offline pipeline: read user://llm_debug/<tag>.txt, run the same
# parse -> sanitize -> validate path the agent uses, print results.
# Iterate the sanitizer/validator without paying qwen3's 60s round-trip.
#
# Usage:
#   godot --headless --path . res://scenes/TestSanitizer.tscn
# Optional override: --tag=initial   (or repair_1, repair_2, ...)

func _ready() -> void:
	var tag := "initial"
	for a in OS.get_cmdline_args():
		if a.begins_with("--tag="):
			tag = a.substr(6)
	var path := "user://llm_debug/%s.txt" % tag
	if not FileAccess.file_exists(path):
		_print_user_dir()
		push_error("missing %s" % path)
		get_tree().quit(1)
		return
	var f := FileAccess.open(path, FileAccess.READ)
	var text := f.get_as_text()
	f.close()
	print("loaded %d chars from %s" % [text.length(), path])

	var parse := _parse_bundle(text)
	if not parse.ok:
		print("PARSE FAIL: ", parse.error)
		get_tree().quit(2); return
	var bundle: Dictionary = parse.bundle
	var san: Dictionary = QuestSanitizer.sanitize(bundle)
	bundle = san.bundle
	var fixes: Array = san.notes
	print("sanitizer fixes: %d" % fixes.size())
	for fx in fixes:
		print("  ~ ", fx)
	var errs: Array = QuestValidator.validate(bundle)
	print("validation errors: %d" % errs.size())
	for e in errs:
		print("  - ", e)
	if errs.is_empty():
		print("=== VALID — sanitizer + validator pass ===")
		get_tree().quit(0)
	else:
		get_tree().quit(3)

func _parse_bundle(text: String) -> Dictionary:
	var t := text.strip_edges()
	if t.begins_with("```"):
		var nl := t.find("\n")
		if nl > 0: t = t.substr(nl + 1)
		if t.ends_with("```"):
			t = t.substr(0, t.length() - 3).strip_edges()
	var first := t.find("{")
	var last := t.rfind("}")
	if first < 0 or last <= first:
		return {"ok": false, "error": "no JSON object"}
	t = t.substr(first, last - first + 1)
	var parsed: Variant = JSON.parse_string(t)
	if not (parsed is Dictionary):
		return {"ok": false, "error": "JSON parse failed"}
	return {"ok": true, "bundle": parsed}

func _print_user_dir() -> void:
	print("user:// resolves to ", OS.get_user_data_dir())
