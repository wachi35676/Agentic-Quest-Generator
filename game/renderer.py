"""Rendering system: tilemap, entities, camera."""

import pygame
from game.world import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT


class Camera:
    """Camera that follows the player with smooth scrolling."""

    def __init__(self, screen_w: int, screen_h: int):
        self.x = 0.0
        self.y = 0.0
        self.screen_w = screen_w
        self.screen_h = screen_h

    def update(self, target_px: float, target_py: float):
        """Center camera on target pixel position."""
        self.x = target_px - self.screen_w // 2
        self.y = target_py - self.screen_h // 2
        # Clamp to world bounds
        max_x = MAP_WIDTH * TILE_SIZE - self.screen_w
        max_y = MAP_HEIGHT * TILE_SIZE - self.screen_h
        self.x = max(0, min(self.x, max_x))
        self.y = max(0, min(self.y, max_y))

    def world_to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        return int(wx - self.x), int(wy - self.y)

    def tile_to_screen(self, tx: int, ty: int) -> tuple[int, int]:
        return int(tx * TILE_SIZE - self.x), int(ty * TILE_SIZE - self.y)

    def is_visible(self, wx: float, wy: float, margin: int = 64) -> bool:
        sx, sy = self.world_to_screen(wx, wy)
        return -margin <= sx <= self.screen_w + margin and -margin <= sy <= self.screen_h + margin


class Renderer:
    """Draws the game world and entities."""

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        sw, sh = screen.get_size()
        self.camera = Camera(sw, sh)
        self.font_zone = pygame.font.Font(None, 18)
        self.font_npc = pygame.font.Font(None, 22)
        self.font_entity = pygame.font.Font(None, 20)

    def render(self, world, player, npcs):
        """Render one frame of the game world."""
        # Update camera
        self.camera.update(player.pixel_x + TILE_SIZE // 2, player.pixel_y + TILE_SIZE // 2)

        sw, sh = self.screen.get_size()

        # Determine visible tile range
        start_tx = max(0, int(self.camera.x // TILE_SIZE))
        start_ty = max(0, int(self.camera.y // TILE_SIZE))
        end_tx = min(MAP_WIDTH, start_tx + sw // TILE_SIZE + 2)
        end_ty = min(MAP_HEIGHT, start_ty + sh // TILE_SIZE + 2)

        # Draw tilemap
        for ty in range(start_ty, end_ty):
            for tx in range(start_tx, end_tx):
                sx, sy = self.camera.tile_to_screen(tx, ty)
                color = world.get_zone_color(tx, ty)
                # Slight grid effect: darken edges
                edge_darken = 10
                base_color = color
                # Checkerboard subtle pattern
                if (tx + ty) % 2 == 0:
                    color = (max(0, color[0] - edge_darken),
                             max(0, color[1] - edge_darken),
                             max(0, color[2] - edge_darken))
                pygame.draw.rect(self.screen, color, (sx, sy, TILE_SIZE, TILE_SIZE))

        # Draw zone boundary lines
        for zone in world.zones:
            x1_s, y1_s = self.camera.tile_to_screen(zone.x1, zone.y1)
            x2_s, y2_s = self.camera.tile_to_screen(zone.x2, zone.y2)
            w = x2_s - x1_s
            h = y2_s - y1_s
            if x2_s > 0 and x1_s < sw and y2_s > 0 and y1_s < sh:
                pygame.draw.rect(self.screen, (40, 40, 40), (x1_s, y1_s, w, h), 1)

        # Draw lore items
        for lore in world.lore_items:
            if lore.collected:
                continue
            sx, sy = self.camera.tile_to_screen(lore.tile_x, lore.tile_y)
            if -32 <= sx <= sw + 32 and -32 <= sy <= sh + 32:
                center = (sx + TILE_SIZE // 2, sy + TILE_SIZE // 2)
                pygame.draw.rect(self.screen, lore.color,
                                 (sx + 8, sy + 8, TILE_SIZE - 16, TILE_SIZE - 16))
                letter_surf = self.font_entity.render("L", True, (0, 0, 0))
                self.screen.blit(letter_surf, (center[0] - letter_surf.get_width() // 2,
                                               center[1] - letter_surf.get_height() // 2))

        # Draw puzzles
        for puzzle in world.puzzles:
            if puzzle.solved:
                continue
            sx, sy = self.camera.tile_to_screen(puzzle.tile_x, puzzle.tile_y)
            if -32 <= sx <= sw + 32 and -32 <= sy <= sh + 32:
                center = (sx + TILE_SIZE // 2, sy + TILE_SIZE // 2)
                pygame.draw.rect(self.screen, puzzle.color,
                                 (sx + 4, sy + 4, TILE_SIZE - 8, TILE_SIZE - 8))
                letter_surf = self.font_entity.render("?", True, (0, 0, 0))
                self.screen.blit(letter_surf, (center[0] - letter_surf.get_width() // 2,
                                               center[1] - letter_surf.get_height() // 2))

        # Draw enemies
        for enemy in world.enemies:
            if not enemy.alive:
                continue
            sx, sy = self.camera.tile_to_screen(enemy.tile_x, enemy.tile_y)
            if -32 <= sx <= sw + 32 and -32 <= sy <= sh + 32:
                center = (sx + TILE_SIZE // 2, sy + TILE_SIZE // 2)
                pygame.draw.circle(self.screen, enemy.color, center, enemy.size // 2)
                # Draw letter
                letter = enemy.display_name[0].upper()
                letter_surf = self.font_entity.render(letter, True, (255, 255, 255))
                self.screen.blit(letter_surf, (center[0] - letter_surf.get_width() // 2,
                                               center[1] - letter_surf.get_height() // 2))
                # Boss indicator
                if enemy.is_boss:
                    pygame.draw.circle(self.screen, (255, 215, 0), center, enemy.size // 2 + 3, 2)

        # Draw NPCs
        for npc in npcs:
            sx, sy = self.camera.tile_to_screen(npc.tile_x, npc.tile_y)
            if -32 <= sx <= sw + 32 and -32 <= sy <= sh + 32:
                center = (sx + TILE_SIZE // 2, sy + TILE_SIZE // 2)
                pygame.draw.circle(self.screen, npc.color, center, npc.size // 2)
                # Draw letter
                letter_surf = self.font_npc.render(npc.letter, True, (0, 0, 0))
                self.screen.blit(letter_surf, (center[0] - letter_surf.get_width() // 2,
                                               center[1] - letter_surf.get_height() // 2))
                # Name above
                name_surf = self.font_entity.render(npc.name, True, (255, 255, 255))
                self.screen.blit(name_surf, (center[0] - name_surf.get_width() // 2,
                                             sy - 14))
                # Interaction indicator if not talked to
                if not npc.talked_to:
                    pygame.draw.circle(self.screen, (255, 255, 0), (center[0], sy - 4), 4)

        # Draw player
        px, py = self.camera.world_to_screen(player.pixel_x, player.pixel_y)
        player_center = (px + TILE_SIZE // 2, py + TILE_SIZE // 2)
        pygame.draw.circle(self.screen, player.color, player_center, player.size // 2)
        # Player inner
        pygame.draw.circle(self.screen, (255, 255, 255), player_center, 6)
