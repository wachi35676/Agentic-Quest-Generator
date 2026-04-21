"""Turn-based combat system."""

import pygame
import random


class CombatState:
    """Manages a combat encounter between player and enemy."""

    PLAYER_TURN = "player_turn"
    ENEMY_TURN = "enemy_turn"
    PLAYER_WON = "player_won"
    PLAYER_FLED = "player_fled"
    PLAYER_DEAD = "player_dead"
    ANIMATING = "animating"

    def __init__(self, player, enemy):
        self.player = player
        self.enemy = enemy
        self.turn = self.PLAYER_TURN
        self.menu_index = 0  # 0=Attack, 1=Use Item, 2=Flee
        self.menu_items = ["Attack", "Use Item", "Flee"]
        self.log: list[str] = []
        self.log.append(f"A wild {enemy.display_name} appears!")
        self.finished = False
        self.result = ""  # "won", "fled", "dead"

        # Animation
        self.anim_timer = 0.0
        self.anim_duration = 0.6
        self.shake_offset = 0
        self.flash_player = False
        self.flash_enemy = False

    def handle_event(self, event) -> bool:
        """Handle combat input. Returns True if combat should end."""
        if self.finished:
            if event.type == pygame.KEYDOWN:
                return True
            return False

        if self.turn != self.PLAYER_TURN:
            return False

        if event.type != pygame.KEYDOWN:
            return False

        if event.key == pygame.K_UP:
            self.menu_index = (self.menu_index - 1) % len(self.menu_items)
        elif event.key == pygame.K_DOWN:
            self.menu_index = (self.menu_index + 1) % len(self.menu_items)
        elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
            self._execute_player_action()

        return False

    def _execute_player_action(self):
        if self.menu_index == 0:
            # Attack
            dmg = max(1, self.player.damage - 2)  # Enemies have some implicit defense
            actual = self.enemy.take_damage(dmg)
            self.log.append(f"You attack {self.enemy.display_name} for {actual} damage!")
            self.flash_enemy = True
            if self.enemy.is_dead():
                self.log.append(f"{self.enemy.display_name} is defeated!")
                self.finished = True
                self.result = "won"
                self.turn = self.PLAYER_WON
                return
        elif self.menu_index == 1:
            # Use Item - find first consumable
            used = False
            for i, item in enumerate(self.player.inventory):
                if item["type"] == "consumable":
                    msg = self.player.use_item(i)
                    if msg:
                        self.log.append(msg)
                        used = True
                    break
            if not used:
                self.log.append("No consumable items!")
                return  # Don't end turn
        elif self.menu_index == 2:
            # Flee
            if random.random() < 0.5:
                self.log.append("You fled successfully!")
                self.finished = True
                self.result = "fled"
                self.turn = self.PLAYER_FLED
                return
            else:
                self.log.append("Failed to flee!")

        # Enemy turn
        if not self.finished:
            self.turn = self.ENEMY_TURN
            self.anim_timer = self.anim_duration

    def update(self, dt: float):
        """Update combat animations and enemy turn."""
        if self.flash_enemy or self.flash_player:
            self.anim_timer -= dt
            if self.anim_timer <= 0:
                self.flash_enemy = False
                self.flash_player = False

        if self.turn == self.ENEMY_TURN:
            self.anim_timer -= dt
            if self.anim_timer <= 0:
                self._enemy_attack()
                self.turn = self.PLAYER_TURN

    def _enemy_attack(self):
        actual = self.player.take_damage(self.enemy.damage)
        self.log.append(f"{self.enemy.display_name} attacks you for {actual} damage!")
        self.flash_player = True
        self.anim_timer = self.anim_duration
        if self.player.is_dead():
            self.log.append("You have been defeated...")
            self.finished = True
            self.result = "dead"
            self.turn = self.PLAYER_DEAD

    def draw(self, surface: pygame.Surface):
        """Draw combat UI."""
        sw, sh = surface.get_size()

        # Dark overlay
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))

        font_title = pygame.font.Font(None, 40)
        font_text = pygame.font.Font(None, 28)
        font_small = pygame.font.Font(None, 22)

        # Title
        title = font_title.render("-- COMBAT --", True, (255, 80, 80))
        surface.blit(title, (sw // 2 - title.get_width() // 2, 30))

        # Enemy display
        enemy_x = sw // 2
        enemy_y = 140
        enemy_color = (255, 100, 100) if not self.flash_enemy else (255, 255, 255)
        size = 50 if self.enemy.is_boss else 36
        pygame.draw.circle(surface, enemy_color, (enemy_x, enemy_y), size)
        letter = self.enemy.display_name[0].upper()
        letter_surf = font_title.render(letter, True, (0, 0, 0))
        surface.blit(letter_surf, (enemy_x - letter_surf.get_width() // 2,
                                   enemy_y - letter_surf.get_height() // 2))

        # Enemy name and HP bar
        name_surf = font_text.render(self.enemy.display_name, True, (255, 200, 200))
        surface.blit(name_surf, (enemy_x - name_surf.get_width() // 2, enemy_y + size + 10))

        bar_w = 200
        bar_h = 16
        bar_x = enemy_x - bar_w // 2
        bar_y = enemy_y + size + 36
        pygame.draw.rect(surface, (80, 0, 0), (bar_x, bar_y, bar_w, bar_h))
        hp_ratio = max(0, self.enemy.hp / self.enemy.max_hp)
        pygame.draw.rect(surface, (200, 0, 0), (bar_x, bar_y, int(bar_w * hp_ratio), bar_h))
        hp_text = font_small.render(f"HP: {self.enemy.hp}/{self.enemy.max_hp}", True, (255, 255, 255))
        surface.blit(hp_text, (bar_x + bar_w // 2 - hp_text.get_width() // 2, bar_y))

        # Player HP bar
        player_y = sh - 280
        p_name = font_text.render("You", True, (100, 200, 255))
        surface.blit(p_name, (80, player_y))
        p_bar_x = 80
        p_bar_y = player_y + 28
        pygame.draw.rect(surface, (0, 60, 0), (p_bar_x, p_bar_y, bar_w, bar_h))
        p_ratio = max(0, self.player.hp / self.player.max_hp)
        pygame.draw.rect(surface, (0, 180, 0), (p_bar_x, p_bar_y, int(bar_w * p_ratio), bar_h))
        p_hp = font_small.render(f"HP: {self.player.hp}/{self.player.max_hp}", True, (255, 255, 255))
        surface.blit(p_hp, (p_bar_x + bar_w // 2 - p_hp.get_width() // 2, p_bar_y))

        if self.flash_player:
            pygame.draw.rect(surface, (255, 0, 0), (p_bar_x - 5, player_y - 5, bar_w + 10, 55), 2)

        # Menu or result
        menu_y = sh - 200
        if not self.finished:
            if self.turn == self.PLAYER_TURN:
                for i, item in enumerate(self.menu_items):
                    color = (255, 255, 100) if i == self.menu_index else (200, 200, 200)
                    prefix = "> " if i == self.menu_index else "  "
                    text_surf = font_text.render(prefix + item, True, color)
                    surface.blit(text_surf, (100, menu_y + i * 32))
            else:
                wait_surf = font_text.render("Enemy is attacking...", True, (255, 150, 150))
                surface.blit(wait_surf, (100, menu_y))
        else:
            if self.result == "won":
                result_surf = font_title.render("VICTORY!", True, (100, 255, 100))
            elif self.result == "fled":
                result_surf = font_title.render("Escaped!", True, (200, 200, 100))
            else:
                result_surf = font_title.render("DEFEATED", True, (255, 50, 50))
            surface.blit(result_surf, (sw // 2 - result_surf.get_width() // 2, menu_y))
            cont_surf = font_small.render("Press any key to continue...", True, (180, 180, 180))
            surface.blit(cont_surf, (sw // 2 - cont_surf.get_width() // 2, menu_y + 50))

        # Combat log (last 4 entries)
        log_y = sh - 80
        visible_log = self.log[-4:]
        for i, entry in enumerate(visible_log):
            log_surf = font_small.render(entry, True, (200, 200, 200))
            surface.blit(log_surf, (60, log_y + i * 18))
