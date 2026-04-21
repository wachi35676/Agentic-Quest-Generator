"""Quest log overlay UI."""

import pygame


class QuestLogUI:
    """Displays quest objectives and sub-quests."""

    def __init__(self):
        self.visible = False
        self.scroll_offset = 0
        self.max_visible_lines = 20

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            self.scroll_offset = 0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
            self.toggle()
        elif event.key == pygame.K_UP:
            self.scroll_offset = max(0, self.scroll_offset - 1)
        elif event.key == pygame.K_DOWN:
            self.scroll_offset += 1

    def draw(self, surface: pygame.Surface, quest_data, player):
        """Draw quest log overlay."""
        if not self.visible:
            return

        sw, sh = surface.get_size()
        # Semi-transparent background
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surface.blit(overlay, (0, 0))

        font_title = pygame.font.Font(None, 40)
        font_heading = pygame.font.Font(None, 30)
        font_text = pygame.font.Font(None, 24)
        font_hint = pygame.font.Font(None, 22)

        lines = []  # (text, font, color, indent)

        # Quest title and description
        lines.append((quest_data.title, font_title, (255, 220, 100), 0))
        lines.append(("", font_text, (0, 0, 0), 0))  # spacer
        # Word-wrap description
        desc_words = quest_data.description.split()
        desc_line = ""
        for word in desc_words:
            test = desc_line + (" " if desc_line else "") + word
            if font_text.size(test)[0] <= sw - 160:
                desc_line = test
            else:
                lines.append((desc_line, font_text, (200, 200, 200), 10))
                desc_line = word
        if desc_line:
            lines.append((desc_line, font_text, (200, 200, 200), 10))

        lines.append(("", font_text, (0, 0, 0), 0))

        # Main objectives
        lines.append(("OBJECTIVES", font_heading, (100, 200, 255), 0))
        for obj in quest_data.objectives:
            check = "[x]" if obj.completed else "[ ]"
            opt = " (optional)" if obj.is_optional else ""
            color = (100, 255, 100) if obj.completed else (220, 220, 220)
            # Show progress for kill/collect
            progress = ""
            if obj.objective_type == "kill" and not obj.completed:
                count = player.kill_counts.get(obj.target, 0)
                progress = f" ({count}/{obj.target_count})"
            elif obj.objective_type == "collect" and not obj.completed:
                count = player.collected_items.get(obj.target, 0)
                progress = f" ({count}/{obj.target_count})"
            elif obj.objective_type == "explore" and not obj.completed:
                if obj.target in player.explored_zones:
                    progress = " (visited)"

            text = f"{check} {obj.description}{opt}{progress}"
            if obj.location:
                text += f"  [{obj.location}]"
            lines.append((text, font_text, color, 20))

        # Sub-quests
        if quest_data.sub_quests:
            lines.append(("", font_text, (0, 0, 0), 0))
            lines.append(("SUB-QUESTS", font_heading, (200, 150, 255), 0))
            for sq in quest_data.sub_quests:
                lines.append((f"  {sq.title}", font_heading, (220, 200, 255), 10))
                lines.append((f"    {sq.description}", font_text, (180, 180, 180), 20))
                for obj in sq.objectives:
                    check = "[x]" if obj.completed else "[ ]"
                    color = (100, 255, 100) if obj.completed else (200, 200, 200)
                    lines.append((f"    {check} {obj.description}", font_text, color, 30))

        # Clamp scroll
        if self.scroll_offset > max(0, len(lines) - self.max_visible_lines):
            self.scroll_offset = max(0, len(lines) - self.max_visible_lines)

        # Render visible lines
        y = 50
        visible = lines[self.scroll_offset:self.scroll_offset + self.max_visible_lines]
        for text, font, color, indent in visible:
            if text:
                surf = font.render(text, True, color)
                surface.blit(surf, (60 + indent, y))
            y += font.get_linesize() + 4

        # Scroll hints
        if self.scroll_offset > 0:
            up_surf = font_hint.render("^ scroll up ^", True, (120, 120, 120))
            surface.blit(up_surf, (sw // 2 - up_surf.get_width() // 2, 30))
        if self.scroll_offset + self.max_visible_lines < len(lines):
            down_surf = font_hint.render("v scroll down v", True, (120, 120, 120))
            surface.blit(down_surf, (sw // 2 - down_surf.get_width() // 2, sh - 30))

        # Controls
        hint = "[Up/Down] Scroll   [Q/Esc] Close"
        hint_surf = font_hint.render(hint, True, (120, 120, 120))
        surface.blit(hint_surf, (sw // 2 - hint_surf.get_width() // 2, sh - 50))
