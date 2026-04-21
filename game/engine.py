"""Main game engine: loop, state machine, event handling."""

import sys
import pygame
import re

from quests.schema import QuestData, EnemyEncounter
from game.world import World
from game.player import Player
from game.renderer import Renderer
from game.npc import NPC, create_npcs_from_quest
from game.combat import CombatState
from game.dialog_ui import DialogUI
from game.inventory import InventoryUI
from game.quest_log_ui import QuestLogUI
from game.hud import HUD
from runtime.events import (
    AdaptationEvent, GameStateSnapshot,
    EVENT_BOSS_DEFEATED, EVENT_AREA_DISCOVERED, EVENT_BRANCHING_CHOICE,
    EVENT_ITEM_ACQUIRED, EVENT_ALL_ENEMIES_CLEARED,
    EVENT_NPC_KILLED, EVENT_REPUTATION_THRESHOLD,
)
from runtime.adapter import RuntimeAdapter


# Game states
STATE_EXPLORATION = "exploration"
STATE_COMBAT = "combat"
STATE_DIALOG = "dialog"
STATE_QUEST_LOG = "quest_log"
STATE_INVENTORY = "inventory"
STATE_PAUSED = "paused"
STATE_GAME_OVER = "game_over"
STATE_VICTORY = "victory"

SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
FPS = 60


class GameEngine:
    """Main game engine that runs the Pygame loop."""

    def __init__(self, quest_filepath: str, pattern=None):
        pygame.init()
        pygame.display.set_caption("Agentic Quest Generator - Adventure")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True

        # Load quest data
        self.quest_data = QuestData.load(quest_filepath)

        # Game state
        self.state = STATE_EXPLORATION
        self.previous_zone = ""

        # World
        self.world = World()
        self.world.place_enemies(self.quest_data.enemies)
        self.world.place_lore_items(self.quest_data.lore_items)
        self.world.place_puzzles(self.quest_data.puzzles)

        # Player — start in village center
        village = self.world.get_zone_for_name("village")
        if village:
            sx, sy = village.center()
        else:
            sx, sy = 30, 37
        self.player = Player(sx, sy)

        # NPCs
        self.npcs = create_npcs_from_quest(self.quest_data, self.world)
        self.world.npcs = self.npcs

        # Subsystems
        self.renderer = Renderer(self.screen)
        self.dialog_ui = DialogUI()
        self.inventory_ui = InventoryUI()
        self.quest_log_ui = QuestLogUI()
        self.hud = HUD()
        self.combat: CombatState | None = None

        # Branching consequences lookup
        self.consequences_map = {}
        for bc in self.quest_data.branching_consequences:
            self.consequences_map[bc.trigger_choice] = bc

        # Give player a starting health potion
        self.player.add_item("Health Potion", "consumable", 3, {"heal": 30})

        # --- Runtime Adapter for real-time quest adaptation ---
        self.adapter: RuntimeAdapter | None = None
        if pattern is not None:
            self.adapter = RuntimeAdapter(pattern)
        self._adaptation_pending_shown = False
        self._last_reputation_threshold = 0  # Track reputation threshold crossings

    def run(self):
        """Main game loop."""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # seconds

            self._handle_events()
            self._update(dt)
            self._render()

            pygame.display.flip()

        pygame.quit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            if self.state == STATE_EXPLORATION:
                self._handle_exploration_event(event)
            elif self.state == STATE_COMBAT:
                self._handle_combat_event(event)
            elif self.state == STATE_DIALOG:
                self._handle_dialog_event(event)
            elif self.state == STATE_INVENTORY:
                self._handle_inventory_event(event)
            elif self.state == STATE_QUEST_LOG:
                self._handle_quest_log_event(event)
            elif self.state == STATE_PAUSED:
                self._handle_pause_event(event)
            elif self.state == STATE_GAME_OVER:
                self._handle_game_over_event(event)
            elif self.state == STATE_VICTORY:
                self._handle_victory_event(event)

    def _handle_exploration_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            self.state = STATE_PAUSED
        elif event.key == pygame.K_i:
            self.inventory_ui.toggle()
            self.state = STATE_INVENTORY
        elif event.key == pygame.K_q:
            self.quest_log_ui.toggle()
            self.state = STATE_QUEST_LOG
        elif event.key in (pygame.K_e, pygame.K_SPACE):
            self._try_interact()

    def _handle_combat_event(self, event):
        if self.combat:
            should_end = self.combat.handle_event(event)
            if should_end:
                self._end_combat()

    def _handle_dialog_event(self, event):
        consequence = self.dialog_ui.handle_event(event)
        if consequence:
            self._apply_consequence(consequence)
        if not self.dialog_ui.active:
            self.state = STATE_EXPLORATION

    def _handle_inventory_event(self, event):
        self.inventory_ui.handle_event(event, self.player)
        if not self.inventory_ui.visible:
            self.state = STATE_EXPLORATION

    def _handle_quest_log_event(self, event):
        self.quest_log_ui.handle_event(event)
        if not self.quest_log_ui.visible:
            self.state = STATE_EXPLORATION

    def _handle_pause_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.state = STATE_EXPLORATION
            elif event.key == pygame.K_q:
                self.running = False

    def _handle_game_over_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                # Restart: reset player
                village = self.world.get_zone_for_name("village")
                if village:
                    sx, sy = village.center()
                else:
                    sx, sy = 30, 37
                self.player.hp = self.player.max_hp
                self.player.tile_x = sx
                self.player.tile_y = sy
                self.player.pixel_x = float(sx * 32)
                self.player.pixel_y = float(sy * 32)
                self.player.moving = False
                self.state = STATE_EXPLORATION
            elif event.key == pygame.K_ESCAPE:
                self.running = False

    def _handle_victory_event(self, event):
        if event.type == pygame.KEYDOWN:
            self.running = False

    def _update(self, dt: float):
        self.hud.update(dt)
        self.inventory_ui.update(dt)

        # --- Check for completed quest adaptations ---
        self._check_adaptation_results()

        if self.state == STATE_EXPLORATION:
            # Handle continuous key presses for movement
            if not self.player.moving:
                keys = pygame.key.get_pressed()
                dx, dy = 0, 0
                if keys[pygame.K_LEFT]:
                    dx = -1
                elif keys[pygame.K_RIGHT]:
                    dx = 1
                elif keys[pygame.K_UP]:
                    dy = -1
                elif keys[pygame.K_DOWN]:
                    dy = 1

                if dx != 0 or dy != 0:
                    self.player.try_move(dx, dy, self.world)

            self.player.update(dt)

            # Check zone transitions
            current_zone = self.world.get_zone_at(self.player.tile_x, self.player.tile_y)
            if current_zone:
                zone_name = current_zone.name
                if zone_name != self.previous_zone:
                    self.previous_zone = zone_name
                    self.hud.set_zone_notification(zone_name)
                    self.player.explored_zones.add(zone_name)
                    # Check explore objectives
                    self._check_explore_objectives(zone_name)
                    # Check dynamic events
                    self._check_dynamic_events(f"enters_zone_{zone_name}")
                    # Emit area_discovered event for adaptation
                    self._emit_adaptation_event(
                        EVENT_AREA_DISCOVERED,
                        {"zone": zone_name},
                    )

            # Check collision with enemies (when player finishes moving to a tile)
            if not self.player.moving:
                enemy = self.world.get_enemy_at(self.player.tile_x, self.player.tile_y)
                if enemy:
                    self._start_combat(enemy)

                # Auto-collect lore items
                lore = self.world.get_lore_at(self.player.tile_x, self.player.tile_y)
                if lore:
                    lore.collected = True
                    self.player.add_item(lore.data.title, "lore", 1)
                    self.hud.set_notification(f"Found lore: {lore.data.title}")
                    self._check_collect_objectives(lore.data.title)
                    # Emit item_acquired event
                    self._emit_adaptation_event(
                        EVENT_ITEM_ACQUIRED,
                        {"item_name": lore.data.title, "item_type": "lore"},
                    )

            # Check victory
            self._check_victory()

        elif self.state == STATE_COMBAT:
            if self.combat:
                self.combat.update(dt)

        elif self.state == STATE_DIALOG:
            self.dialog_ui.update(dt)

    def _try_interact(self):
        """Try to interact with adjacent NPC, puzzle, or lore item."""
        adjacent = self.player.get_adjacent_tiles()
        # Also check current tile
        tiles_to_check = [(self.player.tile_x, self.player.tile_y)] + adjacent

        for tx, ty in tiles_to_check:
            # Check NPCs
            for npc in self.npcs:
                if npc.tile_x == tx and npc.tile_y == ty:
                    if self.dialog_ui.start_dialog(npc):
                        self.state = STATE_DIALOG
                        self.player.interactions.add(npc.npc_id)
                        # Check interact objectives
                        self._check_interact_objectives(npc.npc_id)
                    else:
                        self.hud.set_notification(f"{npc.name} has nothing to say.")
                    return

            # Check puzzles
            puzzle = self.world.get_puzzle_at(tx, ty)
            if puzzle:
                self._try_solve_puzzle(puzzle)
                return

            # Check lore items
            lore = self.world.get_lore_at(tx, ty)
            if lore:
                lore.collected = True
                self.player.add_item(lore.data.title, "lore", 1)
                self.hud.set_notification(f"Found lore: {lore.data.title}")
                self._check_collect_objectives(lore.data.title)
                return

    def _try_solve_puzzle(self, puzzle_entity):
        """Attempt to solve a puzzle."""
        puzzle = puzzle_entity.data
        # Check required items
        if puzzle.required_items:
            for item_name in puzzle.required_items:
                if not self.player.has_item(item_name):
                    self.hud.set_notification(f"Need: {item_name}")
                    return
            # Consume required items
            for item_name in puzzle.required_items:
                self.player.remove_item(item_name)

        puzzle_entity.solved = True
        self.hud.set_notification(f"Puzzle solved! {puzzle.description[:40]}...")

        # Give reward
        if puzzle.reward:
            self.player.add_item(
                puzzle.reward.item_name,
                puzzle.reward.item_type,
                puzzle.reward.quantity,
                puzzle.reward.stats,
            )
            self.hud.set_notification(f"Received: {puzzle.reward.item_name}")

    def _start_combat(self, enemy):
        """Enter combat state."""
        self.combat = CombatState(self.player, enemy)
        self.state = STATE_COMBAT

    def _end_combat(self):
        """Return from combat to exploration."""
        if not self.combat:
            self.state = STATE_EXPLORATION
            return

        if self.combat.result == "won":
            enemy = self.combat.enemy
            enemy.alive = False
            self.player.record_kill(enemy.enemy_type)
            # Check kill objectives
            self._check_kill_objectives(enemy.enemy_type)
            # Drop loot
            for loot_name in enemy.loot_table:
                self.player.add_item(loot_name, "misc", 1)
                self.hud.set_notification(f"Looted: {loot_name}")
            # Check dynamic events
            count = self.player.kill_counts.get(enemy.enemy_type, 0)
            self._check_dynamic_events(f"player_kills_{count}_{enemy.enemy_type}")

            # --- Emit adaptation events for kills ---
            if enemy.is_boss:
                self._emit_adaptation_event(
                    EVENT_BOSS_DEFEATED,
                    {
                        "enemy_type": enemy.enemy_type,
                        "display_name": enemy.display_name,
                        "location": self.previous_zone,
                    },
                )
            else:
                self._emit_adaptation_event(
                    EVENT_NPC_KILLED,
                    {
                        "enemy_type": enemy.enemy_type,
                        "display_name": enemy.display_name,
                        "kill_count": count,
                    },
                )

            # Check if all enemies in the current zone are cleared
            zone = self.world.get_zone_at(self.player.tile_x, self.player.tile_y)
            if zone:
                zone_enemies = [
                    e for e in self.world.enemies
                    if e.alive and zone.contains(e.tile_x, e.tile_y)
                ]
                if not zone_enemies:
                    self._emit_adaptation_event(
                        EVENT_ALL_ENEMIES_CLEARED,
                        {"zone": zone.name},
                    )

            # Emit item_acquired for loot drops
            for loot_name in enemy.loot_table:
                self._emit_adaptation_event(
                    EVENT_ITEM_ACQUIRED,
                    {"item_name": loot_name, "item_type": "loot"},
                )

        elif self.combat.result == "dead":
            self.state = STATE_GAME_OVER
            self.combat = None
            return

        # "fled" - enemy stays alive, player doesn't move
        self.combat = None
        self.state = STATE_EXPLORATION

    def _apply_consequence(self, consequence_str: str):
        """Apply a dialog choice consequence."""
        if not consequence_str:
            return

        old_reputation = self.player.reputation

        # Parse simple consequence strings
        # e.g. "reputation+1", "reputation-2", "unlock_subquest_sq01", "add_item:Sword"
        if consequence_str.startswith("reputation"):
            match = re.match(r"reputation([+-]\d+)", consequence_str)
            if match:
                self.player.reputation += int(match.group(1))
                self.hud.set_notification(f"Reputation: {self.player.reputation:+d}")
        elif consequence_str.startswith("add_item:"):
            item_name = consequence_str[9:]
            self.player.add_item(item_name, "quest_item", 1)
            self.hud.set_notification(f"Received: {item_name}")
            # Emit item_acquired event
            self._emit_adaptation_event(
                EVENT_ITEM_ACQUIRED,
                {"item_name": item_name, "item_type": "quest_item"},
            )
        elif consequence_str.startswith("heal"):
            self.player.heal(30)
            self.hud.set_notification("You feel restored.")

        # Check branching consequences
        if consequence_str in self.consequences_map:
            bc = self.consequences_map[consequence_str]
            self.player.reputation += bc.reputation_effect
            if bc.reputation_effect != 0:
                self.hud.set_notification(f"Reputation: {self.player.reputation:+d}")

        # Emit branching_choice event for any dialog consequence
        self._emit_adaptation_event(
            EVENT_BRANCHING_CHOICE,
            {"choice": consequence_str, "old_reputation": old_reputation},
        )

        # Check reputation threshold crossings (+3 or -3)
        new_threshold = self.player.reputation // 3
        if new_threshold != self._last_reputation_threshold:
            self._last_reputation_threshold = new_threshold
            self._emit_adaptation_event(
                EVENT_REPUTATION_THRESHOLD,
                {
                    "reputation": self.player.reputation,
                    "threshold": new_threshold * 3,
                    "direction": "positive" if self.player.reputation > 0 else "negative",
                },
            )

    # ------------------------------------------------------------------
    # Runtime Adaptation
    # ------------------------------------------------------------------

    def _emit_adaptation_event(self, event_type: str, details: dict):
        """Emit a game event to the runtime adapter for potential quest adaptation."""
        if self.adapter is None:
            return
        try:
            event = AdaptationEvent(event_type=event_type, details=details)
            game_state = GameStateSnapshot.from_player(self.player, self.quest_data)
            self.adapter.on_event(event, game_state, self.quest_data)
            # Show interlude if adaptation is now pending
            if self.adapter.has_pending_adaptation() and not self._adaptation_pending_shown:
                self.hud.set_notification("The winds of fate shift...", 3.0)
                self._adaptation_pending_shown = True
        except Exception:
            pass  # Don't let adaptation errors crash the game

    def _check_adaptation_results(self):
        """Check if an adaptation has completed and apply it."""
        if self.adapter is None:
            return
        modification = self.adapter.get_completed_adaptation()
        if modification is None:
            return

        self._adaptation_pending_shown = False
        self._apply_quest_modification(modification)

    def _apply_quest_modification(self, modification):
        """Apply a QuestModification to the active quest and update the game world."""
        messages = RuntimeAdapter.apply_modification(self.quest_data, modification)

        # Spawn newly added enemies into the world
        for enemy_dict in modification.added_enemies:
            try:
                enc = EnemyEncounter.from_dict(enemy_dict)
                self.world.place_enemies([enc])
            except (KeyError, TypeError, ValueError):
                continue

        # Spawn new NPCs from added dialogs
        if modification.added_dialogs:
            new_npcs = create_npcs_from_quest(self.quest_data, self.world)
            existing_ids = {npc.npc_id for npc in self.npcs}
            for npc in new_npcs:
                if npc.npc_id not in existing_ids:
                    self.npcs.append(npc)
            self.world.npcs = self.npcs

        # Show narrative messages to the player
        for msg in messages:
            if msg:
                self.hud.set_notification(msg[:80], 4.0)

    def _check_kill_objectives(self, enemy_type: str):
        count = self.player.kill_counts.get(enemy_type, 0)
        for obj in self.quest_data.objectives:
            if obj.objective_type == "kill" and obj.target == enemy_type and not obj.completed:
                if count >= obj.target_count:
                    obj.completed = True
                    self.hud.set_notification(f"Objective complete: {obj.description}")
        # Sub-quest objectives
        for sq in self.quest_data.sub_quests:
            for obj in sq.objectives:
                if obj.objective_type == "kill" and obj.target == enemy_type and not obj.completed:
                    if count >= obj.target_count:
                        obj.completed = True
                        self.hud.set_notification(f"Objective complete: {obj.description}")

    def _check_collect_objectives(self, item_name: str):
        count = self.player.collected_items.get(item_name, 0)
        for obj in self.quest_data.objectives:
            if obj.objective_type in ("collect", "deliver") and obj.target == item_name and not obj.completed:
                if count >= obj.target_count:
                    obj.completed = True
                    self.hud.set_notification(f"Objective complete: {obj.description}")
        for sq in self.quest_data.sub_quests:
            for obj in sq.objectives:
                if obj.objective_type in ("collect", "deliver") and obj.target == item_name and not obj.completed:
                    if count >= obj.target_count:
                        obj.completed = True
                        self.hud.set_notification(f"Objective complete: {obj.description}")

    def _check_explore_objectives(self, zone_name: str):
        for obj in self.quest_data.objectives:
            if obj.objective_type == "explore" and not obj.completed:
                if obj.target == zone_name or obj.location == zone_name:
                    obj.completed = True
                    self.hud.set_notification(f"Objective complete: {obj.description}")
        for sq in self.quest_data.sub_quests:
            for obj in sq.objectives:
                if obj.objective_type == "explore" and not obj.completed:
                    if obj.target == zone_name or obj.location == zone_name:
                        obj.completed = True
                        self.hud.set_notification(f"Objective complete: {obj.description}")

    def _check_interact_objectives(self, npc_id: str):
        for obj in self.quest_data.objectives:
            if obj.objective_type == "interact" and obj.target == npc_id and not obj.completed:
                obj.completed = True
                self.hud.set_notification(f"Objective complete: {obj.description}")
        for sq in self.quest_data.sub_quests:
            for obj in sq.objectives:
                if obj.objective_type == "interact" and obj.target == npc_id and not obj.completed:
                    obj.completed = True
                    self.hud.set_notification(f"Objective complete: {obj.description}")

    def _check_dynamic_events(self, trigger: str):
        for event in self.quest_data.dynamic_events:
            if event.trigger == trigger:
                if event.narrative_text:
                    self.hud.set_notification(event.narrative_text[:60], 4.0)
                # Process effects (simple spawning)
                for effect in event.effects:
                    if effect.startswith("spawn_enemy"):
                        # Could spawn additional enemies; skip for simplicity
                        pass

    def _check_victory(self):
        """Check if all required (non-optional) objectives are complete."""
        required = [o for o in self.quest_data.objectives if not o.is_optional]
        if not required:
            return  # No objectives to complete
        all_done = all(o.completed for o in required)
        if all_done:
            self.state = STATE_VICTORY

    def _render(self):
        self.screen.fill((0, 0, 0))

        if self.state in (STATE_EXPLORATION, STATE_COMBAT, STATE_DIALOG,
                          STATE_INVENTORY, STATE_QUEST_LOG, STATE_PAUSED):
            # Draw world
            self.renderer.render(self.world, self.player, self.npcs)

            # Draw HUD
            current_zone = self.world.get_zone_at(self.player.tile_x, self.player.tile_y)
            zone_name = current_zone.name if current_zone else ""
            self.hud.draw(self.screen, self.player, self.world, zone_name)

        # Draw overlays based on state
        if self.state == STATE_COMBAT:
            if self.combat:
                self.combat.draw(self.screen)
        elif self.state == STATE_DIALOG:
            self.dialog_ui.draw(self.screen)
        elif self.state == STATE_INVENTORY:
            self.inventory_ui.draw(self.screen, self.player)
        elif self.state == STATE_QUEST_LOG:
            self.quest_log_ui.draw(self.screen, self.quest_data, self.player)
        elif self.state == STATE_PAUSED:
            self._draw_pause_screen()
        elif self.state == STATE_GAME_OVER:
            self._draw_game_over_screen()
        elif self.state == STATE_VICTORY:
            self._draw_victory_screen()

    def _draw_pause_screen(self):
        sw, sh = self.screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        font_lg = pygame.font.Font(None, 50)
        font_md = pygame.font.Font(None, 30)

        title = font_lg.render("PAUSED", True, (255, 255, 255))
        self.screen.blit(title, (sw // 2 - title.get_width() // 2, sh // 3))

        resume = font_md.render("[Esc] Resume", True, (200, 200, 200))
        self.screen.blit(resume, (sw // 2 - resume.get_width() // 2, sh // 2))

        quit_text = font_md.render("[Q] Quit", True, (200, 200, 200))
        self.screen.blit(quit_text, (sw // 2 - quit_text.get_width() // 2, sh // 2 + 40))

    def _draw_game_over_screen(self):
        sw, sh = self.screen.get_size()
        self.screen.fill((20, 0, 0))

        font_lg = pygame.font.Font(None, 60)
        font_md = pygame.font.Font(None, 30)

        title = font_lg.render("GAME OVER", True, (255, 50, 50))
        self.screen.blit(title, (sw // 2 - title.get_width() // 2, sh // 3))

        retry = font_md.render("[R] Retry  |  [Esc] Quit", True, (200, 200, 200))
        self.screen.blit(retry, (sw // 2 - retry.get_width() // 2, sh // 2 + 30))

    def _draw_victory_screen(self):
        sw, sh = self.screen.get_size()
        self.screen.fill((0, 20, 0))

        font_lg = pygame.font.Font(None, 60)
        font_md = pygame.font.Font(None, 30)
        font_sm = pygame.font.Font(None, 24)

        title = font_lg.render("QUEST COMPLETE!", True, (100, 255, 100))
        self.screen.blit(title, (sw // 2 - title.get_width() // 2, sh // 4))

        quest_title = font_md.render(self.quest_data.title, True, (200, 255, 200))
        self.screen.blit(quest_title, (sw // 2 - quest_title.get_width() // 2, sh // 3 + 20))

        # Show rewards
        if self.quest_data.rewards:
            rewards_text = font_md.render("Rewards:", True, (255, 255, 200))
            self.screen.blit(rewards_text, (sw // 2 - rewards_text.get_width() // 2, sh // 2))
            for i, reward in enumerate(self.quest_data.rewards):
                r_text = f"  {reward.item_name} x{reward.quantity} ({reward.item_type})"
                r_surf = font_sm.render(r_text, True, (220, 220, 180))
                self.screen.blit(r_surf, (sw // 2 - r_surf.get_width() // 2, sh // 2 + 35 + i * 24))

        # Stats
        stats_y = sh * 2 // 3
        kills_total = sum(self.player.kill_counts.values())
        zones_explored = len(self.player.explored_zones)
        stats = [
            f"Enemies defeated: {kills_total}",
            f"Zones explored: {zones_explored}/12",
            f"Items collected: {sum(self.player.collected_items.values())}",
            f"Reputation: {self.player.reputation:+d}",
        ]
        for i, stat in enumerate(stats):
            s_surf = font_sm.render(stat, True, (180, 220, 180))
            self.screen.blit(s_surf, (sw // 2 - s_surf.get_width() // 2, stats_y + i * 24))

        cont = font_md.render("Press any key to exit", True, (150, 150, 150))
        self.screen.blit(cont, (sw // 2 - cont.get_width() // 2, sh - 80))


def run_game(quest_filepath: str, pattern=None):
    """Entry point to run the game with a quest JSON file.

    Args:
        quest_filepath: Path to the quest JSON file.
        pattern: Optional AgenticPattern instance for real-time quest adaptation.
                 If None, the game runs without runtime adaptation.
    """
    engine = GameEngine(quest_filepath, pattern=pattern)
    engine.run()
