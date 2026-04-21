"""Dialog box system with typewriter effect and branching choices."""

import pygame


class DialogUI:
    """Dialog rendering and navigation system."""

    def __init__(self):
        self.active = False
        self.npc = None
        self.dialog_tree = {}
        self.current_node_id = ""
        self.current_line = None  # DialogLine

        # Typewriter effect
        self.full_text = ""
        self.displayed_chars = 0
        self.char_timer = 0.0
        self.chars_per_second = 40.0
        self.text_complete = False

        # Choices
        self.choice_index = 0
        self.chosen_consequence = None  # Set when a choice has a consequence

        # Visual
        self.box_height = 200
        self.padding = 20

    def start_dialog(self, npc):
        """Begin a dialog with an NPC."""
        self.npc = npc
        self.dialog_tree = npc.get_dialog_tree()
        entry = npc.get_entry_node()
        if not entry or entry not in self.dialog_tree:
            # No valid dialog
            self.active = False
            return False
        self.active = True
        self.chosen_consequence = None
        self._load_node(entry)
        npc.talked_to = True
        return True

    def _load_node(self, node_id: str):
        """Load a dialog node."""
        if node_id not in self.dialog_tree:
            self.active = False
            return
        self.current_node_id = node_id
        self.current_line = self.dialog_tree[node_id]
        self.full_text = self.current_line.text
        self.displayed_chars = 0
        self.char_timer = 0.0
        self.text_complete = False
        self.choice_index = 0

    def handle_event(self, event) -> str | None:
        """Handle dialog input. Returns consequence string if a choice was made, else None."""
        if not self.active:
            return None
        if event.type != pygame.KEYDOWN:
            return None

        consequence = None

        if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE or event.key == pygame.K_e:
            if not self.text_complete:
                # Skip typewriter, show full text
                self.displayed_chars = len(self.full_text)
                self.text_complete = True
            elif self.current_line and self.current_line.choices:
                # A choice is selected
                choices = self.current_line.choices
                if 0 <= self.choice_index < len(choices):
                    choice = choices[self.choice_index]
                    consequence = choice.consequence
                    if choice.next_node:
                        self._load_node(choice.next_node)
                    else:
                        self.active = False
                return consequence
            else:
                # Advance to next node
                if self.current_line and self.current_line.next_node:
                    self._load_node(self.current_line.next_node)
                else:
                    self.active = False

        elif event.key == pygame.K_UP:
            if self.text_complete and self.current_line and self.current_line.choices:
                self.choice_index = max(0, self.choice_index - 1)
        elif event.key == pygame.K_DOWN:
            if self.text_complete and self.current_line and self.current_line.choices:
                max_idx = len(self.current_line.choices) - 1
                self.choice_index = min(max_idx, self.choice_index + 1)
        elif event.key == pygame.K_ESCAPE:
            self.active = False

        return consequence

    def update(self, dt: float):
        """Update typewriter effect."""
        if not self.active or self.text_complete:
            return
        self.char_timer += dt * self.chars_per_second
        while self.char_timer >= 1.0 and self.displayed_chars < len(self.full_text):
            self.displayed_chars += 1
            self.char_timer -= 1.0
        if self.displayed_chars >= len(self.full_text):
            self.text_complete = True

    def draw(self, surface: pygame.Surface):
        """Draw dialog box at the bottom of the screen."""
        if not self.active or not self.current_line:
            return

        sw, sh = surface.get_size()
        box_y = sh - self.box_height
        box_rect = pygame.Rect(0, box_y, sw, self.box_height)

        # Background
        dialog_bg = pygame.Surface((sw, self.box_height), pygame.SRCALPHA)
        dialog_bg.fill((20, 20, 40, 230))
        surface.blit(dialog_bg, (0, box_y))
        pygame.draw.rect(surface, (100, 100, 180), box_rect, 2)

        font_name = pygame.font.Font(None, 30)
        font_text = pygame.font.Font(None, 26)
        font_choice = pygame.font.Font(None, 24)

        # Speaker name
        speaker = self.current_line.speaker
        name_color = (100, 200, 255) if speaker.lower() != "player" else (100, 255, 100)
        name_surf = font_name.render(speaker, True, name_color)
        surface.blit(name_surf, (self.padding + 10, box_y + 12))

        # Dialog text with typewriter effect
        visible_text = self.full_text[:self.displayed_chars]
        # Word wrap
        self._draw_wrapped_text(surface, font_text, visible_text,
                                self.padding + 10, box_y + 42, sw - 2 * self.padding - 20,
                                (230, 230, 230))

        # Choices
        if self.text_complete and self.current_line.choices:
            choices = self.current_line.choices
            choice_y = box_y + self.box_height - 20 - len(choices) * 26
            for i, choice in enumerate(choices):
                is_sel = i == self.choice_index
                prefix = "> " if is_sel else "  "
                color = (255, 255, 100) if is_sel else (180, 180, 180)
                choice_surf = font_choice.render(prefix + choice.text, True, color)
                surface.blit(choice_surf, (self.padding + 20, choice_y + i * 26))
        elif self.text_complete:
            # Advance hint
            hint = font_choice.render("[Enter] to continue", True, (120, 120, 120))
            surface.blit(hint, (sw - hint.get_width() - 20, box_y + self.box_height - 28))

    def _draw_wrapped_text(self, surface, font, text, x, y, max_width, color):
        """Draw text with simple word wrapping."""
        words = text.split(' ')
        lines = []
        current_line = ""
        for word in words:
            test = current_line + (" " if current_line else "") + word
            if font.size(test)[0] <= max_width:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        line_height = font.get_linesize()
        for i, line in enumerate(lines[:4]):  # Max 4 lines
            surf = font.render(line, True, color)
            surface.blit(surf, (x, y + i * line_height))
