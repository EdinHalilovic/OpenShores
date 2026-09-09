
from __future__ import annotations

from openshores.core.heartbeat_watch import _note_0x18
from openshores.core.logging import get_logger
from openshores.protocol.atoms.effect import _build_player_effect_atom_pkt
from openshores.protocol.framing import write_framed
from openshores.world.sim_time_low import _current_sim_t_low

logger = get_logger(__name__)


async def _push_player_effect(writer, player_auid: int,
                              origin_xyz=(0.0, 0.0, 0.0),
                              sound_type=0x5F,
                              visual_type=0x1E,
                              *,
                              _live_avatars,
                              anchor_full,
                              anchor_low32,
                              sim_time_state,
                              next_effect_time_ms,
                              _stamina_byte,
                              agent_bits_for):
    if writer is None:
        try:
            _entry = _live_avatars.get(int(player_auid) & 0xFFFFFFFF)
            if _entry:
                writer = _entry.get("writer")
        except Exception:
            logger.debug(f"[fire-fx] auid={player_auid!r} writer lookup "
                         f"failed")
            writer = None
    if writer is None:
        logger.debug(f"[fire-fx] auid=0x{int(player_auid):08x} skip writer=None (and not found in _live_avatars)")
        return
    try:
        if writer.is_closing():
            logger.debug(f"[fire-fx] auid=0x{int(player_auid):08x} skip writer is_closing")
            return
    except Exception as _ce:
        logger.debug(f"[fire-fx] auid=0x{int(player_auid):08x} skip is_closing raised: {_ce!r}")
        return
    try:
        _sync_t_low = _note_0x18((_current_sim_t_low(anchor_full=anchor_full)
                                  or sim_time_state.get("last_0x18_t_low", 0)
                                  or anchor_low32),
                                 "player-effect-sync")
        if _sync_t_low:
            _sync_pkt = (bytes([0x18])
                         + (_sync_t_low & 0xFFFFFFFF).to_bytes(4, "big")
                         + bytes([0x02]))
            await write_framed(writer, _sync_pkt)
            sim_time_state["last_0x18_t_low"] = _sync_t_low & 0xFFFFFFFF
        body = _build_player_effect_atom_pkt(
            int(player_auid),
            origin_xyz=origin_xyz,
            sound_type=int(sound_type),
            visual_type=int(visual_type),
            next_effect_time_ms=next_effect_time_ms,
            _stamina_byte=_stamina_byte,
            agent_bits_for=agent_bits_for,
        )
        await write_framed(writer, body)
        _wire_u16_dbg = int.from_bytes(body[16:18], "big")
        logger.debug(
            f"[fire-fx] auid=0x{int(player_auid):08x} "
            f"sound=0x{int(sound_type):02x} visual=0x{int(visual_type):02x} "
            f"origin={origin_xyz} sent={len(body)}B "
            f"wire_u16=0x{_wire_u16_dbg:04x} "
            f"last_0x18_t_low="
            f"0x{sim_time_state.get('last_0x18_t_low', 0):08x} "
            f"anchor_low32=0x{anchor_low32:08x}")
    except Exception as _pe_e:
        logger.error(f"[fire-fx] write err: {_pe_e!r}")
