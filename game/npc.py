"""NPC entities with dialog interaction."""

import random


class NPC:
    """An NPC entity in the world."""

    def __init__(self, npc_id: str, name: str, tile_x: int, tile_y: int, dialog_data=None):
        self.npc_id = npc_id
        self.name = name
        self.tile_x = tile_x
        self.tile_y = tile_y
        self.dialog_data = dialog_data  # NPCDialog schema object
        self.talked_to = False
        # Visual: colored circle with first letter
        self.color = (100, 200, 100)
        self.size = 26
        self.letter = name[0].upper() if name else "?"

    def get_dialog_tree(self) -> dict:
        """Return the dialog tree as a dict keyed by node_id."""
        if not self.dialog_data or not self.dialog_data.dialog_tree:
            return {}
        tree = {}
        for line in self.dialog_data.dialog_tree:
            tree[line.node_id] = line
        return tree

    def get_entry_node(self) -> str:
        """Return the entry node ID."""
        if self.dialog_data and self.dialog_data.entry_node:
            return self.dialog_data.entry_node
        if self.dialog_data and self.dialog_data.dialog_tree:
            return self.dialog_data.dialog_tree[0].node_id
        return ""


def create_npcs_from_quest(quest_data, world) -> list[NPC]:
    """Create NPC entities from quest data and place them in the world."""
    npcs = []
    for dialog in quest_data.npc_dialogs:
        zone = world.get_zone_for_name(dialog.location)
        if zone:
            tx, ty = zone.random_position(margin=3)
            # Avoid placing on occupied tiles
            attempts = 0
            while world._tile_occupied(tx, ty) and attempts < 10:
                tx, ty = zone.random_position(margin=3)
                attempts += 1
        else:
            # Fallback: place in village
            village = world.get_zone_for_name("village")
            if village:
                tx, ty = village.random_position(margin=3)
            else:
                tx, ty = 30, 37
        npc = NPC(
            npc_id=dialog.npc_id,
            name=dialog.npc_name,
            tile_x=tx,
            tile_y=ty,
            dialog_data=dialog,
        )
        npcs.append(npc)
    return npcs
