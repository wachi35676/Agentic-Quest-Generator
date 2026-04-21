"""Always-visible HUD: HP bar, zone name, minimap, reputation."""

import pygame
from game.world import ZONE_GRID, ZONE_COLORS, MAP_COLS, MAP_ROWS, ZONE_WIDTH, ZONE_HEIGHT


class HUD:
    """Heads-up display drawn on top of the game view."""

    def __init__(self):
        self.zone_notification = ""
        self.zone_notify_timer = 0.0
        self.notification_text = ""
        self.notification_timer = 0.0

    def set_zone_notification(self, zone_name: str):
        """Show a zone entry notification."""
        self.zone_notification = zone_name
        self.zone_notify_timer = 3.0

    def set_notification(self, text: str, duration: float = 3.0):
        """Show a general notification."""
        self.notification_text = text
        self.notification_timer = duration

    def update(self, dt: float):
        if self.zone_notify_timer > 0:
            self.zone_notify_timer -= dt
            if self.zone_notify_timer <= 0:
                self.zone_notification = ""
        if self.notification_timer > 0:
            self.notification_timer -= dt
            if self.notification_timer <= 0:
                self.notification_text = ""

    def draw(self, surface: pygame.Surface, player, world, current_zone_name: str):
        sw, sh = surface.get_size()
        font_sm = pygame.font.Font(None, 22)
        font_md = pygame.font.Font(None, 28)
        font_lg = pygame.font.Font(None, 36)

        # HP Bar (top-left)
        hp_bar_x = 10
        hp_bar_y = 10
        hp_bar_w = 200
        hp_bar_h = 20
        pygame.draw.rect(surface, (60, 0, 0), (hp_bar_x, hp_bar_y, hp_bar_w, hp_bar_h))
        hp_ratio = max(0, player.hp / player.max_hp)
        hp_color = (0, 200, 0) if hp_ratio > 0.5 else (200, 200, 0) if hp_ratio > 0.25 else (200, 0, 0)
        pygame.draw.rect(surface, hp_color, (hp_bar_x, hp_bar_y, int(hp_bar_w * hp_ratio), hp_bar_h))
        pygame.draw.rect(surface, (200, 200, 200), (hp_bar_x, hp_bar_y, hp_bar_w, hp_bar_h), 1)
        hp_text = font_sm.render(f"HP: {player.hp}/{player.max_hp}", True, (255, 255, 255))
        surface.blit(hp_text, (hp_bar_x + hp_bar_w // 2 - hp_text.get_width() // 2,
                               hp_bar_y + 1))

        # Current zone name (top-center)
        zone_display = current_zone_name.replace("_", " ").title() if current_zone_name else "Unknown"
        zone_surf = font_md.render(zone_display, True, (220, 220, 220))
        surface.blit(zone_surf, (sw // 2 - zone_surf.get_width() // 2, 10))

        # Reputation (below HP)
        rep_text = f"Rep: {player.reputation:+d}" if player.reputation != 0 else "Rep: 0"
        rep_color = (100, 255, 100) if player.reputation > 0 else (255, 100, 100) if player.reputation < 0 else (200, 200, 200)
        rep_surf = font_sm.render(rep_text, True, rep_color)
        surface.blit(rep_surf, (10, hp_bar_y + hp_bar_h + 6))

        # Minimap (top-right)
        mm_tile = 6  # pixels per zone on minimap
        mm_w = MAP_COLS * mm_tile
        mm_h = MAP_ROWS * mm_tile
        mm_x = sw - mm_w - 10
        mm_y = 10
        # Background
        pygame.draw.rect(surface, (20, 20, 20), (mm_x - 1, mm_y - 1, mm_w + 2, mm_h + 2))

        for row_idx, row in enumerate(ZONE_GRID):
            for col_idx, zone_name in enumerate(row):
                color = ZONE_COLORS.get(zone_name, (60, 60, 60))
                rx = mm_x + col_idx * mm_tile
                ry = mm_y + row_idx * mm_tile
                pygame.draw.rect(surface, color, (rx, ry, mm_tile - 1, mm_tile - 1))

        # Player dot on minimap
        px = mm_x + int((player.tile_x / (MAP_COLS * ZONE_WIDTH)) * mm_w)
        py = mm_y + int((player.tile_y / (MAP_ROWS * ZONE_HEIGHT)) * mm_h)
        pygame.draw.circle(surface, (255, 255, 255), (px, py), 2)
        pygame.draw.rect(surface, (180, 180, 180), (mm_x - 1, mm_y - 1, mm_w + 2, mm_h + 2), 1)

        # Zone entry notification
        if self.zone_notification:
            alpha = min(255, int(self.zone_notify_timer / 0.5 * 255)) if self.zone_notify_timer < 0.5 else 255
            notify_surf = font_lg.render(f"Entering: {self.zone_notification.replace('_', ' ').title()}",
                                         True, (255, 255, 200))
            # Center horizontally, upper third
            nx = sw // 2 - notify_surf.get_width() // 2
            ny = sh // 4
            surface.blit(notify_surf, (nx, ny))

        # General notification
        if self.notification_text:
            notify_surf = font_md.render(self.notification_text, True, (255, 255, 100))
            nx = sw // 2 - notify_surf.get_width() // 2
            ny = sh // 3 + 30
            surface.blit(notify_surf, (nx, ny))

        # Controls hint (bottom)
        hint = "Arrow:Move  E/Space:Interact  I:Inventory  Q:Quest Log  Esc:Pause"
        hint_surf = font_sm.render(hint, True, (100, 100, 100))
        surface.blit(hint_surf, (sw // 2 - hint_surf.get_width() // 2, sh - 22))
