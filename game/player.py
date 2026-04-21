"""Player character with stats, inventory, and grid movement."""

import pygame


class Player:
    """The player character."""

    def __init__(self, x: int = 30, y: int = 37):
        # Tile position
        self.tile_x = x
        self.tile_y = y
        # Pixel position for smooth movement
        self.pixel_x = float(x * 32)
        self.pixel_y = float(y * 32)
        # Movement
        self.moving = False
        self.target_tile_x = x
        self.target_tile_y = y
        self.move_speed = 160.0  # pixels per second

        # Stats
        self.hp = 100
        self.max_hp = 100
        self.damage = 15
        self.defense = 5
        self.reputation = 0

        # Inventory: list of dicts with name, type, quantity, stats
        self.inventory = []

        # Tracking
        self.kill_counts = {}  # enemy_type -> count
        self.explored_zones = set()
        self.collected_items = {}  # item_name -> count
        self.interactions = set()  # npc_ids interacted with

        # Visual
        self.color = (0, 150, 255)
        self.size = 28

    def take_damage(self, amount: int) -> int:
        """Take damage reduced by defense. Returns actual damage taken."""
        actual = max(1, amount - self.defense)
        self.hp = max(0, self.hp - actual)
        return actual

    def heal(self, amount: int):
        """Heal the player."""
        self.hp = min(self.max_hp, self.hp + amount)

    def is_dead(self) -> bool:
        return self.hp <= 0

    def add_item(self, name: str, item_type: str = "misc", quantity: int = 1, stats: dict | None = None):
        """Add an item to inventory."""
        for item in self.inventory:
            if item["name"] == name and item["type"] == item_type:
                item["quantity"] += quantity
                break
        else:
            self.inventory.append({
                "name": name,
                "type": item_type,
                "quantity": quantity,
                "stats": stats or {},
            })
        # Track for objectives
        self.collected_items[name] = self.collected_items.get(name, 0) + quantity

    def remove_item(self, name: str, quantity: int = 1) -> bool:
        """Remove item from inventory. Returns True if successful."""
        for item in self.inventory:
            if item["name"] == name and item["quantity"] >= quantity:
                item["quantity"] -= quantity
                if item["quantity"] <= 0:
                    self.inventory.remove(item)
                return True
        return False

    def has_item(self, name: str, quantity: int = 1) -> bool:
        """Check if player has enough of an item."""
        for item in self.inventory:
            if item["name"] == name and item["quantity"] >= quantity:
                return True
        return False

    def use_item(self, index: int) -> str | None:
        """Use a consumable item by inventory index. Returns message or None."""
        if index < 0 or index >= len(self.inventory):
            return None
        item = self.inventory[index]
        if item["type"] != "consumable":
            return f"{item['name']} cannot be used."
        # Heal effect
        heal_amount = item["stats"].get("heal", 20)
        self.heal(heal_amount)
        item["quantity"] -= 1
        msg = f"Used {item['name']}. Healed {heal_amount} HP."
        if item["quantity"] <= 0:
            self.inventory.remove(item)
        return msg

    def try_move(self, dx: int, dy: int, world):
        """Start moving to an adjacent tile if not already moving and target is valid."""
        if self.moving:
            return
        new_x = self.tile_x + dx
        new_y = self.tile_y + dy
        if world.is_walkable(new_x, new_y):
            self.target_tile_x = new_x
            self.target_tile_y = new_y
            self.moving = True

    def update(self, dt: float):
        """Update smooth movement. dt is seconds since last frame."""
        if not self.moving:
            return

        target_px = float(self.target_tile_x * 32)
        target_py = float(self.target_tile_y * 32)

        dx = target_px - self.pixel_x
        dy = target_py - self.pixel_y
        dist = (dx * dx + dy * dy) ** 0.5

        step = self.move_speed * dt
        if step >= dist:
            self.pixel_x = target_px
            self.pixel_y = target_py
            self.tile_x = self.target_tile_x
            self.tile_y = self.target_tile_y
            self.moving = False
        else:
            self.pixel_x += (dx / dist) * step
            self.pixel_y += (dy / dist) * step

    def get_facing_tile(self) -> tuple[int, int]:
        """Return the tile the player last moved toward (for interaction).
        If not moving, default to the tile to the right."""
        if self.target_tile_x != self.tile_x or self.target_tile_y != self.tile_y:
            dx = self.target_tile_x - self.tile_x
            dy = self.target_tile_y - self.tile_y
        else:
            dx, dy = 0, -1  # default: face up
        return self.tile_x + dx, self.tile_y + dy

    def get_adjacent_tiles(self) -> list[tuple[int, int]]:
        """Return all 4 adjacent tiles."""
        return [
            (self.tile_x - 1, self.tile_y),
            (self.tile_x + 1, self.tile_y),
            (self.tile_x, self.tile_y - 1),
            (self.tile_x, self.tile_y + 1),
        ]

    def record_kill(self, enemy_type: str):
        self.kill_counts[enemy_type] = self.kill_counts.get(enemy_type, 0) + 1
