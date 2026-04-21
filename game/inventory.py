"""Inventory UI overlay."""

import pygame


class InventoryUI:
    """Inventory management screen overlay."""

    def __init__(self):
        self.visible = False
        self.selected_index = 0
        self.scroll_offset = 0
        self.max_visible = 12
        self.use_message = ""
        self.use_message_timer = 0.0

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            self.selected_index = 0
            self.scroll_offset = 0

    def handle_event(self, event, player) -> str | None:
        """Handle input in inventory mode. Returns a message string or None."""
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_i or event.key == pygame.K_ESCAPE:
            self.toggle()
            return None

        items = player.inventory
        if not items:
            return None

        if event.key == pygame.K_UP:
            self.selected_index = max(0, self.selected_index - 1)
            if self.selected_index < self.scroll_offset:
                self.scroll_offset = self.selected_index
        elif event.key == pygame.K_DOWN:
            self.selected_index = min(len(items) - 1, self.selected_index + 1)
            if self.selected_index >= self.scroll_offset + self.max_visible:
                self.scroll_offset = self.selected_index - self.max_visible + 1
        elif event.key == pygame.K_RETURN:
            msg = player.use_item(self.selected_index)
            if msg:
                self.use_message = msg
                self.use_message_timer = 2.0
                # Clamp selection after removal
                if self.selected_index >= len(player.inventory):
                    self.selected_index = max(0, len(player.inventory) - 1)
            return msg

        return None

    def update(self, dt: float):
        if self.use_message_timer > 0:
            self.use_message_timer -= dt
            if self.use_message_timer <= 0:
                self.use_message = ""

    def draw(self, surface: pygame.Surface, player):
        """Draw inventory overlay."""
        if not self.visible:
            return

        sw, sh = surface.get_size()
        # Semi-transparent background
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        font_title = pygame.font.Font(None, 40)
        font_item = pygame.font.Font(None, 28)
        font_hint = pygame.font.Font(None, 22)

        # Title
        title_surf = font_title.render("INVENTORY", True, (255, 255, 255))
        surface.blit(title_surf, (sw // 2 - title_surf.get_width() // 2, 40))

        items = player.inventory
        if not items:
            empty_surf = font_item.render("Your inventory is empty.", True, (180, 180, 180))
            surface.blit(empty_surf, (sw // 2 - empty_surf.get_width() // 2, 120))
        else:
            y_start = 90
            visible_items = items[self.scroll_offset:self.scroll_offset + self.max_visible]
            for i, item in enumerate(visible_items):
                actual_idx = i + self.scroll_offset
                is_selected = actual_idx == self.selected_index
                # Background highlight
                rect_y = y_start + i * 40
                if is_selected:
                    pygame.draw.rect(surface, (60, 60, 120), (100, rect_y, sw - 200, 36), border_radius=4)
                # Item text
                type_tag = f"[{item['type']}]" if item['type'] != 'misc' else ""
                text = f"{item['name']} x{item['quantity']}  {type_tag}"
                color = (255, 255, 100) if is_selected else (220, 220, 220)
                text_surf = font_item.render(text, True, color)
                surface.blit(text_surf, (120, rect_y + 6))

                # Show stats if selected
                if is_selected and item.get("stats"):
                    stats_str = "  ".join(f"{k}: {v}" for k, v in item["stats"].items())
                    stats_surf = font_hint.render(stats_str, True, (180, 180, 255))
                    surface.blit(stats_surf, (140, rect_y + 28))

            # Scroll indicators
            if self.scroll_offset > 0:
                up_surf = font_hint.render("^ more above ^", True, (150, 150, 150))
                surface.blit(up_surf, (sw // 2 - up_surf.get_width() // 2, y_start - 18))
            if self.scroll_offset + self.max_visible < len(items):
                down_surf = font_hint.render("v more below v", True, (150, 150, 150))
                surface.blit(down_surf, (sw // 2 - down_surf.get_width() // 2, y_start + self.max_visible * 40 + 4))

        # Use message
        if self.use_message:
            msg_surf = font_item.render(self.use_message, True, (100, 255, 100))
            surface.blit(msg_surf, (sw // 2 - msg_surf.get_width() // 2, sh - 120))

        # Controls hint
        hint = "[Up/Down] Navigate   [Enter] Use   [I/Esc] Close"
        hint_surf = font_hint.render(hint, True, (150, 150, 150))
        surface.blit(hint_surf, (sw // 2 - hint_surf.get_width() // 2, sh - 60))
