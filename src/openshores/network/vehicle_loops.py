
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay.vehicles.atom_packet import (
    build_da_vehicle_keepalive,
    build_da_vehicle_update,
)
from openshores.gameplay.vehicles.combat import get_last_damage_ms
from openshores.gameplay.vehicles.spawn import (
    get_active_vehicle,
    list_active_vehicles,
)
from openshores.gameplay.vehicles.ticker import tick_all, tock_all
from openshores.network.vehicle_mount import _veh_reassert_occupants
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


_VEH_KEEPALIVE_TASKS: dict = {}


async def _davehicle_keepalive(vehicle_auid_int: int, *,
                               _live_avatars) -> None:
    period = 0.25
    _first_emit = True
    _emit_count = 0
    try:
        while True:
            try:
                _v_live = get_active_vehicle(vehicle_auid_int)
                if _v_live is None:
                    logger.info(f"[davehicle-keepalive] STOP auid=0x{vehicle_auid_int:08x} "
                                f"(not in active registry; emitted {_emit_count}x)")
                    return
                try:
                    pkt = build_da_vehicle_keepalive(_v_live)
                except Exception as _ke:
                    logger.warning(f"[davehicle-keepalive]   auid=0x{vehicle_auid_int:08x} "
                                   f"build failed: {_ke!r}")
                    await asyncio.sleep(period)
                    continue
                _sent = 0
                for _peer_auid, _peer_entry in list(_live_avatars.items()):
                    _pw = _peer_entry.get("writer")
                    if _pw is None or _pw.is_closing():
                        continue
                    try:
                        await write_framed(_pw, pkt)
                        _sent += 1
                    except Exception as _kae:
                        logger.debug(f"[davehicle-keepalive]   auid=0x{vehicle_auid_int:08x}"
                                     f" emit to peer 0x{_peer_auid:08x} failed: "
                                     f"{_kae!r}")
                _emit_count += 1
                if _first_emit:
                    logger.info(f"[davehicle-keepalive] first EMIT auid=0x{vehicle_auid_int:08x} -> {_sent} peer(s), {len(pkt)}B (period={period}s)")
                    _first_emit = False
                await asyncio.sleep(period)
            except asyncio.CancelledError:
                raise
            except Exception as _iter_exc:
                logger.error(f"[davehicle-keepalive] auid=0x{vehicle_auid_int:08x} "
                             f"iteration failed (continuing): {_iter_exc!r}")
                await asyncio.sleep(period)
                continue
    except asyncio.CancelledError:
        return


def _davehicle_keepalive_start(vehicle_auid_int: int, *,
                               _live_avatars) -> None:
    prior = _VEH_KEEPALIVE_TASKS.pop(vehicle_auid_int, None)
    if prior is not None and not prior.done():
        prior.cancel()
    try:
        task = asyncio.create_task(
            _davehicle_keepalive(vehicle_auid_int,
                                 _live_avatars=_live_avatars))
        _VEH_KEEPALIVE_TASKS[vehicle_auid_int] = task
        logger.info(f"[davehicle-keepalive] STARTED auid=0x{vehicle_auid_int:08x}")
    except RuntimeError as _ke:
        logger.warning(f"[davehicle-keepalive] start failed (no loop) auid=0x{vehicle_auid_int:08x}: {_ke!r}")


async def _veh_physics_tick_loop(*, conn, _live_avatars,
                                 _PLAYER_MOUNTED_VEHICLE,
                                 _VEH_LAST_BROADCAST_POS):
    _period = 0.05
    _eps = 0.5
    logger.info(f"[vehicles-physics] tick loop started "
                f"(period={_period}s, broadcast_eps={_eps}m)")
    try:
        while True:
            try:
                await asyncio.sleep(_period)
                _driven_now = set()
                try:
                    for _pa, _vi in _PLAYER_MOUNTED_VEHICLE.items():
                        _driven_now.add(int(_vi) & 0xFFFFFFFF)
                except Exception as _de:
                    logger.debug("[vehicles-physics] driven-vehicle set unreadable; no "
                                 "vehicle is treated as driven this tick: %r", _de)
                try:
                    await tick_all(skip_ids=_driven_now, conn=conn)
                except Exception as _te:
                    logger.error(f"[vehicles-physics] tick_all failed: {_te!r}")
                    continue
                if not _live_avatars:
                    continue
                _veh_to_driver = {}
                try:
                    for _pa, _vi in _PLAYER_MOUNTED_VEHICLE.items():
                        _veh_to_driver[int(_vi) & 0xFFFFFFFF] = (
                            int(_pa) & 0xFFFFFFFF)
                except Exception as _ie:
                    logger.debug("[vehicles-physics] driver map unreadable; no vehicle "
                                 "is excluded from its own driver this tick: %r", _ie)
                _pkts = []
                for _v in list_active_vehicles():
                    _id = int(_v.id)
                    _last = _VEH_LAST_BROADCAST_POS.get(_id)
                    _moved = (_last is None or
                              abs(_v.locX - _last[0]) > _eps or
                              abs(_v.locY - _last[1]) > _eps or
                              abs(_v.locZ - _last[2]) > _eps)
                    _dmg_ts = 0
                    try:
                        _dmg_ts = int(_veh_get_dmg_ts(_id))
                    except Exception:
                        _dmg_ts = 0
                    _last_dmg_seen = int(
                        _VEH_LAST_BROADCAST_DMG_TS.get(_id, 0))
                    _damaged = (_dmg_ts > 0 and _dmg_ts > _last_dmg_seen)
                    if not (_moved or _damaged):
                        continue
                    try:
                        _pkts.append((_veh_to_driver.get(_id, 0),
                                      build_da_vehicle_update(_v)))
                    except Exception as _be:
                        logger.warning(f"[vehicles-physics] build_update failed "
                                       f"for 0x{_id:08x}: {_be!r}")
                        continue
                    if _moved:
                        _VEH_LAST_BROADCAST_POS[_id] = (_v.locX, _v.locY, _v.locZ)
                    if _damaged:
                        _VEH_LAST_BROADCAST_DMG_TS[_id] = _dmg_ts
                        logger.debug(f"[vehicles-physics] eager broadcast for "
                                     f"damage 0x{_id:08x} ts={_dmg_ts} hp={_v.hp} "
                                     f"switches=0x{int(_v.switches):02x}")
                if not _pkts:
                    continue
                for _peer_auid, _peer_entry in list(_live_avatars.items()):
                    _pw = _peer_entry.get("writer")
                    if _pw is None or _pw.is_closing():
                        continue
                    _peer_int = int(_peer_auid) & 0xFFFFFFFF
                    for _drv_auid, _pkt in _pkts:
                        if _drv_auid and _peer_int == _drv_auid:
                            continue
                        try:
                            await write_framed(_pw, _pkt)
                        except Exception as _we:
                            logger.debug(f"[vehicles-physics] emit to peer "
                                         f"0x{_peer_auid:08x} failed: {_we!r}")
                            break
            except asyncio.CancelledError:
                raise
            except Exception as _iter_exc:
                logger.error(f"[vehicles-physics] tick iteration failed "
                             f"(continuing): {_iter_exc!r}")
                await asyncio.sleep(_period)
                continue
    except asyncio.CancelledError:
        logger.info("[vehicles-physics] tick loop cancelled")


async def _veh_physics_tock_loop(*, conn, _live_avatars,
                                 _PLAYER_MOUNTED_VEHICLE,
                                 _stamina_byte, agent_bits_for):
    _period = 1.0
    logger.info(f"[vehicles-physics] tock loop started (period={_period}s)")
    try:
        while True:
            try:
                await asyncio.sleep(_period)
                try:
                    await tock_all(conn=conn)
                except Exception as _te:
                    logger.error(f"[vehicles-physics] tock_all failed: {_te!r}")
                try:
                    await _veh_reassert_occupants(
                        live_avatars=_live_avatars,
                        player_mounted_vehicle=_PLAYER_MOUNTED_VEHICLE,
                        _stamina_byte=_stamina_byte,
                        agent_bits_for=agent_bits_for)
                except Exception as _oe:
                    logger.warning(f"[vehicles-physics] occupant re-assert failed: "
                                   f"{_oe!r}")
            except asyncio.CancelledError:
                raise
            except Exception as _iter_exc:
                logger.error(f"[vehicles-physics] tock iteration failed "
                             f"(continuing): {_iter_exc!r}")
                await asyncio.sleep(_period)
                continue
    except asyncio.CancelledError:
        logger.info("[vehicles-physics] tock loop cancelled")


_VEH_LAST_BROADCAST_DMG_TS: dict[int, int] = {}


def _veh_get_dmg_ts(vid: int) -> int:
    try:
        return int(get_last_damage_ms(int(vid) & 0xFFFFFFFF))
    except Exception as _ge:
        logger.debug("Damage stamp for vehicle %r unreadable; treated as no damage: %r", vid, _ge)
        return 0
