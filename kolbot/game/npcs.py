"""
NPC interaction and lookup.

Maps NPC IDs to names, provides helpers for finding NPCs in town,
and handles NPC menu interactions (buy, sell, repair, heal, identify,
gamble, hire merc, etc.).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from kolbot.core.game_state import GameStateTracker
from kolbot.core.memory import GameMemoryReader
from kolbot.core.packets import PacketSender
from kolbot.core.structures import MonsterUnit, Position, UnitType
from kolbot.game.map import Area
from kolbot.utils.helpers import distance
from kolbot.utils.logger import get_logger

log = get_logger("game.npcs")


# ===================================================================
# NPC IDs (txtFileNo for important NPCs)
# ===================================================================

class NPC:
    """Well-known NPC identifiers (txtFileNo)."""
    # Act 1
    AKARA = 148
    GHEED = 147
    CHARSI = 154
    KASHYA = 150
    WARRIV_A1 = 155
    CAIN_A1 = 146

    # Act 2
    FARA = 178
    LYSANDER = 199
    DROGNAN = 177
    ELZIX = 199
    GREIZ = 198
    JERHYN = 201
    MESHIF_A2 = 210
    ATMA = 176
    CAIN_A2 = 244
    WARRIV_A2 = 175

    # Act 3
    ORMUS = 255
    ALKOR = 254
    HRATLI = 253
    ASHEARA = 252
    CAIN_A3 = 245
    MESHIF_A3 = 264

    # Act 4
    HALBU = 257
    TYRAEL_A4 = 258
    JAMELLA = 405
    CAIN_A4 = 246

    # Act 5
    LARZUK = 511
    QUAL_KEHK = 515
    MALAH = 513
    ANYA = 512
    NIHLATHAK_NPC = 526
    CAIN_A5 = 527

    # Special
    TYRAEL_A2 = 251  # Act 2 Tyrael


# ===================================================================
# NPC Roles
# ===================================================================

@dataclass(frozen=True, slots=True)
class NPCRole:
    """What services an NPC provides."""
    npc_id: int
    name: str
    act: int
    heals: bool = False
    sells_potions: bool = False
    sells_scrolls: bool = False
    repairs: bool = False
    gambles: bool = False
    identifies: bool = False
    hires_merc: bool = False
    resurrects_merc: bool = False


# NPC service registry
NPC_ROLES: dict[int, NPCRole] = {
    NPC.AKARA: NPCRole(NPC.AKARA, "Akara", 1, heals=True, sells_potions=True, sells_scrolls=True, identifies=True),
    NPC.CHARSI: NPCRole(NPC.CHARSI, "Charsi", 1, repairs=True),
    NPC.GHEED: NPCRole(NPC.GHEED, "Gheed", 1, gambles=True),
    NPC.KASHYA: NPCRole(NPC.KASHYA, "Kashya", 1, hires_merc=True),
    NPC.CAIN_A1: NPCRole(NPC.CAIN_A1, "Cain", 1, identifies=True),
    NPC.FARA: NPCRole(NPC.FARA, "Fara", 2, heals=True, repairs=True),
    NPC.DROGNAN: NPCRole(NPC.DROGNAN, "Drognan", 2, sells_scrolls=True),
    NPC.LYSANDER: NPCRole(NPC.LYSANDER, "Lysander", 2, sells_potions=True),
    NPC.ELZIX: NPCRole(NPC.ELZIX, "Elzix", 2, gambles=True),
    NPC.GREIZ: NPCRole(NPC.GREIZ, "Greiz", 2, hires_merc=True, resurrects_merc=True),
    NPC.CAIN_A2: NPCRole(NPC.CAIN_A2, "Cain", 2, identifies=True),
    NPC.ORMUS: NPCRole(NPC.ORMUS, "Ormus", 3, heals=True, sells_potions=True, sells_scrolls=True),
    NPC.HRATLI: NPCRole(NPC.HRATLI, "Hratli", 3, repairs=True),
    NPC.ALKOR: NPCRole(NPC.ALKOR, "Alkor", 3, gambles=True),
    NPC.ASHEARA: NPCRole(NPC.ASHEARA, "Asheara", 3, hires_merc=True, resurrects_merc=True),
    NPC.CAIN_A3: NPCRole(NPC.CAIN_A3, "Cain", 3, identifies=True),
    NPC.HALBU: NPCRole(NPC.HALBU, "Halbu", 4, repairs=True),
    NPC.JAMELLA: NPCRole(NPC.JAMELLA, "Jamella", 4, heals=True, sells_potions=True, gambles=True),
    NPC.CAIN_A4: NPCRole(NPC.CAIN_A4, "Cain", 4, identifies=True),
    NPC.MALAH: NPCRole(NPC.MALAH, "Malah", 5, heals=True, sells_potions=True, sells_scrolls=True),
    NPC.LARZUK: NPCRole(NPC.LARZUK, "Larzuk", 5, repairs=True),
    NPC.ANYA: NPCRole(NPC.ANYA, "Anya", 5, gambles=True),
    NPC.QUAL_KEHK: NPCRole(NPC.QUAL_KEHK, "Qual-Kehk", 5, hires_merc=True, resurrects_merc=True),
    NPC.CAIN_A5: NPCRole(NPC.CAIN_A5, "Cain", 5, identifies=True),
}


class NPCManager:
    """
    High-level NPC interaction manager.

    Finds NPCs in the current area, interacts with them, and performs
    common actions like shopping, repairing, identifying, etc.
    """

    def __init__(
        self,
        reader: GameMemoryReader,
        sender: PacketSender,
        tracker: GameStateTracker,
    ) -> None:
        self._reader = reader
        self._sender = sender
        self._tracker = tracker

    def find_npc(self, npc_id: int) -> Optional[MonsterUnit]:
        """Find an NPC by txtFileNo in the current monster list."""
        for m in self._tracker.snapshot.monsters:
            if m.txt_file_no == npc_id:
                return m
        return None

    def find_npc_by_role(self, act: int, *, heals: bool = False,
                          repairs: bool = False, gambles: bool = False,
                          identifies: bool = False, sells_potions: bool = False,
                          resurrects_merc: bool = False) -> Optional[int]:
        """Find an NPC ID by role and act."""
        for npc_id, role in NPC_ROLES.items():
            if role.act != act:
                continue
            if heals and not role.heals:
                continue
            if repairs and not role.repairs:
                continue
            if gambles and not role.gambles:
                continue
            if identifies and not role.identifies:
                continue
            if sells_potions and not role.sells_potions:
                continue
            if resurrects_merc and not role.resurrects_merc:
                continue
            return npc_id
        return None

    def interact_npc(self, npc_id: int) -> bool:
        """Walk to and interact with an NPC."""
        npc = self.find_npc(npc_id)
        if not npc:
            log.warning("NPC %d not found in current area", npc_id)
            return False

        self._sender.interact(UnitType.MONSTER, npc.unit_id)
        time.sleep(0.5)
        return True

    def open_trade(self, npc_id: int) -> bool:
        """Interact with NPC and open trade menu."""
        npc = self.find_npc(npc_id)
        if not npc:
            return False

        self._sender.interact(UnitType.MONSTER, npc.unit_id)
        time.sleep(0.3)
        self._sender.send_raw(
            self._sender.builder.npc_init(UnitType.MONSTER, npc.unit_id)
        )
        time.sleep(0.5)
        return True

    def close_npc(self) -> bool:
        """Close the current NPC interaction."""
        # Send NPC_CANCEL with type=1, id=0 to close any open NPC menu
        self._sender.send_raw(
            self._sender.builder.npc_cancel(1, 0)
        )
        time.sleep(0.2)
        return True

    def buy_potions(self, npc_id: int, health_count: int = 0,
                     mana_count: int = 0) -> int:
        """
        Buy potions from an NPC vendor.

        Returns the number of potions bought.
        """
        if not self.open_trade(npc_id):
            return 0

        bought = 0
        # In practice, we'd need to read the NPC's shop inventory
        # and send buy packets for specific items.  This is a framework
        # for the full implementation.
        log.info("Buy potions: health=%d mana=%d (framework)", health_count, mana_count)

        self.close_npc()
        return bought

    def repair_all(self, npc_id: int) -> bool:
        """Repair all items at a repair NPC."""
        if not self.open_trade(npc_id):
            return False

        # Send repair packet (specific to D2 repair NPCs)
        # Repair All = NPC_BUY with special item_id
        log.info("Repair all at NPC %d (framework)", npc_id)

        self.close_npc()
        return True

    def identify_at_cain(self, act: int) -> bool:
        """Identify all items at Deckard Cain."""
        cain_map = {
            1: NPC.CAIN_A1,
            2: NPC.CAIN_A2,
            3: NPC.CAIN_A3,
            4: NPC.CAIN_A4,
            5: NPC.CAIN_A5,
        }
        cain_id = cain_map.get(act)
        if not cain_id:
            return False

        if not self.interact_npc(cain_id):
            return False

        time.sleep(0.5)
        self.close_npc()
        return True

    def resurrect_merc(self, act: int) -> bool:
        """Resurrect mercenary at the appropriate NPC for the act."""
        npc_id = self.find_npc_by_role(act, resurrects_merc=True)
        if not npc_id:
            log.warning("No merc resurrection NPC for act %d", act)
            return False
        return self.interact_npc(npc_id)

    def get_healer_id(self, act: int) -> Optional[int]:
        return self.find_npc_by_role(act, heals=True)

    def get_repair_id(self, act: int) -> Optional[int]:
        return self.find_npc_by_role(act, repairs=True)

    def get_potion_vendor_id(self, act: int) -> Optional[int]:
        return self.find_npc_by_role(act, sells_potions=True)
