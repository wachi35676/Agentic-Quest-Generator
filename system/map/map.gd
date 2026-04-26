@icon("../map/icon_map.png")
extends Node2D
class_name Map

# Stripped-down version of the reference NinjaAdventure Map base. The
# original wired environment-area shader swaps and a screen-grid overlay;
# we don't need either. This just hides the helper rect on _ready.

@onready var screen_grid_ref: TextureRect = $ScreenGridRef


func _ready() -> void:
	if screen_grid_ref:
		screen_grid_ref.visible = false
