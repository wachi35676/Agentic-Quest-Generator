class_name AnimUtil
extends RefCounted

# Ninja Adventure SeparateAnim convention:
#   columns = directions (down, up, left, right)
#   rows    = animation frames (1 row for Idle/Attack, 4 rows for Walk)
const DIRS := ["down", "up", "left", "right"]

static func build_4dir(tex: Texture2D, state: String, frame_w: int, frame_h: int, fps: float, frames_override: int = -1, sf: SpriteFrames = null) -> SpriteFrames:
	if sf == null:
		sf = SpriteFrames.new()
	if tex == null:
		return sf
	var img_w: int = tex.get_width()
	var img_h: int = tex.get_height()
	var cols: int = max(1, img_w / frame_w)   # = directions
	var rows: int = max(1, img_h / frame_h)   # = frames
	var frames: int = rows
	if frames_override > 0:
		frames = min(frames, frames_override) if frames_override <= rows else frames
		frames = frames_override
	var num_dirs: int = min(4, cols)
	for dir_idx in range(num_dirs):
		var anim_name := "%s_%s" % [state, DIRS[dir_idx]]
		if not sf.has_animation(anim_name):
			sf.add_animation(anim_name)
		sf.set_animation_speed(anim_name, fps)
		sf.set_animation_loop(anim_name, true)
		# Drop any existing frames so re-builds don't duplicate
		while sf.get_frame_count(anim_name) > 0:
			sf.remove_frame(anim_name, 0)
		for frame_idx in range(min(frames, rows)):
			var atlas := AtlasTexture.new()
			atlas.atlas = tex
			atlas.region = Rect2(dir_idx * frame_w, frame_idx * frame_h, frame_w, frame_h)
			sf.add_frame(anim_name, atlas)
	return sf

static func dir_name_from_vec(v: Vector2i) -> String:
	if v.y > 0: return "down"
	if v.y < 0: return "up"
	if v.x < 0: return "left"
	return "right"
