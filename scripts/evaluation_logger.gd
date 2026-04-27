extends Node

# Autoload. Writes structured JSONL events to user://eval/<session_id>.jsonl
# whenever AGQ_EVAL is set in the environment OR `--eval` is on the command
# line. No-op otherwise. Used by the offline Python harness in tools/eval/
# to compute the five paper metrics.
#
# Schema: one JSON object per line, fields:
#   { session_id, timestamp_ms, event_type, agent, payload }
#
# Public API:
#   EvaluationLogger.log(event_type, agent, payload)
#   EvaluationLogger.session_id() -> String
#   EvaluationLogger.is_enabled() -> bool
#   EvaluationLogger.start_ms() -> int
#   EvaluationLogger.flush()

var _enabled: bool = false
var _session_id: String = ""
var _profile: String = "manual"
var _file: FileAccess = null
var _start_ms: int = 0

func _ready() -> void:
	# Detect eval mode from env or CLI. We accept either so a one-off
	# manual playtest can be logged via env, while batch runs use both.
	var env_set: bool = OS.get_environment("AGQ_EVAL") != ""
	var cli_set: bool = "--eval" in OS.get_cmdline_args()
	if not (env_set or cli_set):
		return
	_enabled = true
	var profile_env: String = OS.get_environment("AGQ_PROFILE")
	if profile_env != "":
		_profile = profile_env
	_session_id = _make_session_id()
	var dir := DirAccess.open("user://")
	if dir == null:
		push_error("EvaluationLogger: user:// dir not accessible")
		_enabled = false
		return
	if not dir.dir_exists("eval"):
		dir.make_dir("eval")
	var path := "user://eval/%s.jsonl" % _session_id
	_file = FileAccess.open(path, FileAccess.WRITE)
	if _file == null:
		push_error("EvaluationLogger: cannot open %s" % path)
		_enabled = false
		return
	_start_ms = Time.get_ticks_msec()
	print("[eval] logging to ", path)

func log(event_type: String, agent: String, payload: Dictionary) -> void:
	if not _enabled or _file == null:
		return
	var entry := {
		"session_id": _session_id,
		"timestamp_ms": Time.get_ticks_msec(),
		"event_type": event_type,
		"agent": agent,
		"payload": payload,
	}
	_file.store_line(JSON.stringify(entry))
	# Keep file flushed so a Godot crash mid-session still leaves a
	# parseable jsonl behind for the runner to pick up.
	_file.flush()

func session_id() -> String:
	return _session_id

func is_enabled() -> bool:
	return _enabled

func start_ms() -> int:
	return _start_ms

func profile() -> String:
	return _profile

func flush() -> void:
	if _file != null:
		_file.flush()

func _make_session_id() -> String:
	var d := Time.get_datetime_dict_from_system()
	var stem := "%04d%02d%02d_%02d%02d%02d" % [d.year, d.month, d.day, d.hour, d.minute, d.second]
	return "%s_%s" % [stem, _profile]
