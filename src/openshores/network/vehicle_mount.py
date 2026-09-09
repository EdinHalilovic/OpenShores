
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay.vehicles.atom_packet import build_da_vehicle_update
from openshores.gameplay.vehicles.explosion_visuals import _EXPLOSION_VISUAL_BY_CID
from openshores.gameplay.vehicles.spawn import get_active_vehicle
from openshores.network.broadcast import _broadcast_to_peers
from openshores.protocol.atoms.person import _build_daperson_parent_update

logger = get_logger(__name__)


async def _finalize_vehicle_mount(player_auid: int,
                                  vehicle_auid: int,
                                  *,
                                  live_avatars: dict,
                                  _stamina_byte,
                                  agent_bits_for) -> None:
    try:
        _vc = get_active_vehicle(int(vehicle_auid))
    except Exception:
        _vc = None
    if _vc is None:
        logger.warning(f"[mount] vehicle 0x{int(vehicle_auid):08x} not active; "
              f"skipping mount broadcast for player "
              f"0x{int(player_auid):08x}")
        return

    try:
        _vc.switches = int(_vc.switches) | 0x04
    except Exception as _se:
        logger.warning(f"[mount] could not set mounted bit on vehicle "
                       f"0x{int(vehicle_auid):08x}: {_se!r}")
    try:
        _vpkt = build_da_vehicle_update(_vc)
        _sent_v = await _broadcast_to_peers(_vpkt, live_avatars or {})
        logger.info(f"[mount] vehicle 0x{int(_vc.id):08x} 0x1C broadcast -> "
              f"{_sent_v} peer(s) (switches=0x{int(_vc.switches):02x})")
    except Exception as _be:
        logger.error(f"[mount] vehicle broadcast err: {_be!r}")

    try:
        _vid = int(_vc.id) & 0xFFFFFFFF
        _ppkt0 = _build_daperson_parent_update(
            int(player_auid), _vid,
            _stamina_byte=_stamina_byte, agent_bits_for=agent_bits_for)
        _sent = await _broadcast_to_peers(_ppkt0, live_avatars or {})
        logger.info(f"[mount] DaPerson parent 0x{int(player_auid):08x} -> "
              f"0x{_vid:08x} broadcast to {_sent} peer(s) (1/3)")

        async def _mount_parent_retry():
            for _i in (2, 3):
                try:
                    await asyncio.sleep(0.2)
                    _ppkt_i = _build_daperson_parent_update(
                        int(player_auid), _vid,
                        _stamina_byte=_stamina_byte,
                        agent_bits_for=agent_bits_for)
                    _s = await _broadcast_to_peers(
                        _ppkt_i, live_avatars or {})
                    logger.debug(f"[mount] DaPerson parent retry "
                          f"({_i}/3) -> {_s} peer(s)")
                except Exception as _re:
                    logger.error(f"[mount] parent retry {_i} err: {_re!r}")

        asyncio.create_task(_mount_parent_retry())
    except Exception as _pe:
        logger.error(f"[mount] DaPerson parent update err: {_pe!r}")


async def _veh_reassert_occupants(*, live_avatars: dict,
                                  player_mounted_vehicle: dict,
                                  _stamina_byte,
                                  agent_bits_for) -> int:
    try:
        _items = list(player_mounted_vehicle.items())
    except Exception as _ie:
        logger.warning(f"[occupant-sync] mount table unreadable: {_ie!r}")
        return 0
    if not _items:
        return 0
    _n = 0
    for _pa, _vi in _items:
        try:
            _vid = int(_vi) & 0xFFFFFFFF
            if get_active_vehicle(_vid) is None:
                continue
            _ppkt = _build_daperson_parent_update(
                int(_pa), _vid,
                _stamina_byte=_stamina_byte, agent_bits_for=agent_bits_for)
            await _broadcast_to_peers(_ppkt, live_avatars or {})
            _n += 1
        except Exception as _re:
            logger.error(f"[occupant-sync] re-assert err for player "
                  f"0x{int(_pa):08x}: {_re!r}")
    return _n


_EXPLOSION_VISUAL_DEFAULT = 0x18
_EXPLOSION_SOUND_DEFAULT = 0x12


def _explosion_visual_for_vehicle(vc) -> int:
    try:
        return int(_EXPLOSION_VISUAL_BY_CID.get(
            int(vc.cid) & 0xFFFF, _EXPLOSION_VISUAL_DEFAULT)) & 0xFF
    except Exception:
        return _EXPLOSION_VISUAL_DEFAULT
