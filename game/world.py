"""Tilemap world with zones, NPC and enemy placement."""

import random

# Zone colors
ZONE_COLORS = {
    "village": (139, 195, 74),
    "dark_forest": (27, 94, 32),
    "mountain_pass": (158, 158, 158),
    "ancient_ruins": (161, 136, 127),
    "swamp": (85, 139, 47),
    "castle": (120, 120, 120),
    "cave_system": (66, 66, 66),
    "marketplace": (255, 183, 77),
    "graveyard": (97, 97, 97),
    "river_crossing": (66, 165, 245),
    "abandoned_mine": (121, 85, 72),
    "tower": (171, 71, 188),
}

# Zone display names
ZONE_DISPLAY_NAMES = {
    "village": "Village",
    "dark_forest": "Dark Forest",
    "mountain_pass": "Mountain Pass",
    "ancient_ruins": "Ancient Ruins",
    "swamp": "Swamp",
    "castle": "Castle",
    "cave_system": "Cave System",
    "marketplace": "Marketplace",
    "graveyard": "Graveyard",
    "river_crossing": "River Crossing",
    "abandoned_mine": "Abandoned Mine",
    "tower": "Tower",
}

# Zone layout in a 4x3 grid, each zone is 20x15 tiles
# Total map: 60 wide x 60 tall
#   Col 0 (0-19)    Col 1 (20-39)       Col 2 (40-59)
# Row 0 (0-14):   tower          mountain_pass    castle
# Row 1 (15-29):  dark_forest    river_crossing   graveyard
# Row 2 (30-44):  swamp          village          ancient_ruins
# Row 3 (45-59):  cave_system    marketplace      abandoned_mine

ZONE_GRID = [
    ["tower", "mountain_pass", "castle"],
    ["dark_forest", "river_crossing", "graveyard"],
    ["swamp", "village", "ancient_ruins"],
    ["cave_system", "marketplace", "abandoned_mine"],
]

ZONE_WIDTH = 20
ZONE_HEIGHT = 15
MAP_COLS = 3
MAP_ROWS = 4
MAP_WIDTH = ZONE_WIDTH * MAP_COLS   # 60
MAP_HEIGHT = ZONE_HEIGHT * MAP_ROWS  # 60
TILE_SIZE = 32


class Zone:
    """A rectangular zone on the map."""

    def __init__(self, name: str, grid_col: int, grid_row: int):
        self.name = name
        self.display_name = ZONE_DISPLAY_NAMES.get(name, name.replace("_", " ").title())
        self.color = ZONE_COLORS.get(name, (128, 128, 128))
        self.grid_col = grid_col
        self.grid_row = grid_row
        # Tile boundaries
        self.x1 = grid_col * ZONE_WIDTH
        self.y1 = grid_row * ZONE_HEIGHT
        self.x2 = self.x1 + ZONE_WIDTH
        self.y2 = self.y1 + ZONE_HEIGHT

    def contains(self, tx: int, ty: int) -> bool:
        return self.x1 <= tx < self.x2 and self.y1 <= ty < self.y2

    def center(self) -> tuple[int, int]:
        return self.x1 + ZONE_WIDTH // 2, self.y1 + ZONE_HEIGHT // 2

    def random_position(self, margin: int = 2) -> tuple[int, int]:
        """Return a random tile position within the zone, with margin from edges."""
        x = random.randint(self.x1 + margin, self.x2 - margin - 1)
        y = random.randint(self.y1 + margin, self.y2 - margin - 1)
        return x, y


class EnemyEntity:
    """A live enemy on the map."""

    def __init__(self, encounter_data, tile_x: int, tile_y: int, instance_id: int):
        self.encounter = encounter_data  # EnemyEncounter schema object
        self.tile_x = tile_x
        self.tile_y = tile_y
        self.instance_id = instance_id
        self.hp = encounter_data.hp
        self.max_hp = encounter_data.hp
        self.damage = encounter_data.damage
        self.display_name = encounter_data.display_name
        self.enemy_type = encounter_data.enemy_type
        self.is_boss = encounter_data.is_boss
        self.loot_table = list(encounter_data.loot_table)
        self.alive = True
        # Visual
        if self.is_boss:
            self.color = (200, 0, 0)
            self.size = 30
        else:
            self.color = (180, 50, 50)
            self.size = 24

    def take_damage(self, amount: int) -> int:
        actual = max(1, amount)
        self.hp = max(0, self.hp - actual)
        if self.hp <= 0:
            self.alive = False
        return actual

    def is_dead(self) -> bool:
        return not self.alive


class LoreItemEntity:
    """A lore item on the map."""

    def __init__(self, lore_data, tile_x: int, tile_y: int):
        self.data = lore_data
        self.tile_x = tile_x
        self.tile_y = tile_y
        self.collected = False
        self.color = (255, 215, 0)  # gold


class PuzzleEntity:
    """A puzzle on the map."""

    def __init__(self, puzzle_data, tile_x: int, tile_y: int):
        self.data = puzzle_data
        self.tile_x = tile_x
        self.tile_y = tile_y
        self.solved = False
        self.color = (0, 200, 200)  # cyan


class World:
    """The tile-based game world."""

    def __init__(self):
        self.zones: list[Zone] = []
        self.zone_map: dict[str, Zone] = {}
        self.enemies: list[EnemyEntity] = []
        self.npcs = []  # NPC objects (set externally)
        self.lore_items: list[LoreItemEntity] = []
        self.puzzles: list[PuzzleEntity] = []

        # Build zones
        for row_idx, row in enumerate(ZONE_GRID):
            for col_idx, zone_name in enumerate(row):
                zone = Zone(zone_name, col_idx, row_idx)
                self.zones.append(zone)
                self.zone_map[zone_name] = zone

    def get_zone_at(self, tx: int, ty: int) -> Zone | None:
        """Get the zone that contains the given tile position."""
        col = tx // ZONE_WIDTH
        row = ty // ZONE_HEIGHT
        if 0 <= col < MAP_COLS and 0 <= row < MAP_ROWS:
            zone_name = ZONE_GRID[row][col]
            return self.zone_map.get(zone_name)
        return None

    def get_zone_color(self, tx: int, ty: int) -> tuple[int, int, int]:
        zone = self.get_zone_at(tx, ty)
        if zone:
            return zone.color
        return (30, 30, 30)

    def is_walkable(self, tx: int, ty: int) -> bool:
        """Check if a tile is walkable (within map bounds)."""
        return 0 <= tx < MAP_WIDTH and 0 <= ty < MAP_HEIGHT

    def get_zone_for_name(self, name: str) -> Zone | None:
        """Get a zone by name."""
        return self.zone_map.get(name)

    def place_enemies(self, enemy_encounters):
        """Place enemies from quest data onto the map."""
        instance_id = 0
        for enc in enemy_encounters:
            zone = self.zone_map.get(enc.location)
            if not zone:
                # Place in a random zone
                zone = random.choice(self.zones)
            for i in range(enc.count):
                tx, ty = zone.random_position(margin=2)
                # Avoid stacking on exact same tile
                attempts = 0
                while self._tile_occupied(tx, ty) and attempts < 10:
                    tx, ty = zone.random_position(margin=2)
                    attempts += 1
                enemy = EnemyEntity(enc, tx, ty, instance_id)
                self.enemies.append(enemy)
                instance_id += 1

    def place_lore_items(self, lore_items_data):
        """Place lore items from quest data onto the map."""
        for lore in lore_items_data:
            zone = self.zone_map.get(lore.location)
            if not zone:
                zone = random.choice(self.zones)
            tx, ty = zone.random_position(margin=2)
            self.lore_items.append(LoreItemEntity(lore, tx, ty))

    def place_puzzles(self, puzzles_data):
        """Place puzzles from quest data onto the map."""
        for puzzle in puzzles_data:
            zone = self.zone_map.get(puzzle.location)
            if not zone:
                zone = random.choice(self.zones)
            tx, ty = zone.random_position(margin=2)
            self.puzzles.append(PuzzleEntity(puzzle, tx, ty))

    def _tile_occupied(self, tx: int, ty: int) -> bool:
        """Check if a tile already has an enemy or NPC."""
        for e in self.enemies:
            if e.alive and e.tile_x == tx and e.tile_y == ty:
                return True
        for npc in self.npcs:
            if npc.tile_x == tx and npc.tile_y == ty:
                return True
        return False

    def get_enemy_at(self, tx: int, ty: int) -> EnemyEntity | None:
        for e in self.enemies:
            if e.alive and e.tile_x == tx and e.tile_y == ty:
                return e
        return None

    def get_lore_at(self, tx: int, ty: int) -> LoreItemEntity | None:
        for item in self.lore_items:
            if not item.collected and item.tile_x == tx and item.tile_y == ty:
                return item
        return None

    def get_puzzle_at(self, tx: int, ty: int) -> PuzzleEntity | None:
        for p in self.puzzles:
            if not p.solved and p.tile_x == tx and p.tile_y == ty:
                return p
        return None

    def get_alive_enemies(self) -> list[EnemyEntity]:
        return [e for e in self.enemies if e.alive]
