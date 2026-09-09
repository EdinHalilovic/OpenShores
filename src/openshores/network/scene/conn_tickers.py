
from __future__ import annotations

import asyncio

from openshores.core.heartbeat_watch import _note_0x18
from openshores.core.logging import get_logger
from openshores.gameplay import damageable as _sweep_dmg
from openshores.gameplay import story_npc as _npc
from openshores.gameplay.natives import village as _nat
from openshores.gameplay.story_state import _purge_story_npc_state
from openshores.protocol.framing import write_framed
from openshores.world.sim_time import _SIM_TIME_RATE
from openshores.world.sim_time_low import _current_sim_t_low

logger = get_logger(__name__)


async def _ticker_eager(w, *,
                        anchor_full,
                        sim_time_state):
    try:
        while not w.is_closing():
            t_low = _note_0x18(_current_sim_t_low(anchor_full=anchor_full),
                               "ticker_eager", w)
            tp = (bytes([0x18])
                  + t_low.to_bytes(4, "big")
                  + bytes([0x02]))
            await write_framed(w, tp)
            sim_time_state["last_0x18_t_low"] = t_low
            await asyncio.sleep(0.25)
    except Exception as _e:
        logger.info(f"[scene]   ticker_eager ended: {_e!r}")


def start_ticker_eager(writer, _conn_label, *,
                       _conn_tasks,
                       anchor_full,
                       anchor_low32,
                       sim_time_state) -> None:
    _conn_tasks.append(asyncio.create_task(
        _ticker_eager(writer, anchor_full=anchor_full,
                      sim_time_state=sim_time_state)))
    _mode = (
        f"advancing@{_SIM_TIME_RATE:.0f}u/s"
        if anchor_low32 else
        "monotonic-fallback"
    )
    logger.info(f"[scene]   -> {_conn_label} ticker started "
                f"(4 Hz, 0x18 flag=2 heartbeat, {_mode})")


async def _manifest_ticker(w, label, *,
                           _manifest_refresh):
    _emit_fails = 0
    try:
        while not w.is_closing():
            _sleep_for = (
                min(5.0, _manifest_refresh
                    * (2 ** min(_emit_fails, 4)))
                if _emit_fails
                else _manifest_refresh)
            await asyncio.sleep(_sleep_for)
            _builder = getattr(
                w, "_scene_manifest_builder", None)
            if _builder is None:
                continue
            try:
                _mpkt = _builder()
                await write_framed(w, _mpkt)
                _emit_fails = 0
            except (ConnectionResetError,
                    BrokenPipeError,
                    ConnectionAbortedError) as _mte:
                _emit_fails += 1
                if _emit_fails <= 3:
                    logger.warning(f"[manifest-tick] {label} "
                                   f"emit err: {_mte!r} "
                                   f"(fail #{_emit_fails}, "
                                   f"continuing)")
                continue
            except Exception as _mte:
                _emit_fails += 1
                logger.warning(f"[manifest-tick] {label} "
                               f"emit err: {_mte!r} "
                               f"(fail #{_emit_fails}, "
                               f"continuing)")
                continue
    except Exception as _mtx:
        logger.info(f"[manifest-tick] {label} ended: {_mtx!r}")


def start_manifest_ticker(writer, _conn_label, *, _conn_tasks) -> None:
    _manifest_refresh = 5.0
    _conn_tasks.append(asyncio.create_task(
        _manifest_ticker(writer, _conn_label,
                         _manifest_refresh=_manifest_refresh)))
    logger.info(f'[scene]   -> {_conn_label} manifest ticker started (every {_manifest_refresh:.1f}s, 0x18 flag=1.')


async def _natives_idle_ticker(w, label, conn, *,
                               _nat_idle_sec):
    while True:
        await asyncio.sleep(_nat_idle_sec)
        if w.is_closing():
            return
        try:
            _ents = await _nat.build_native_idle_entries(conn)
        except Exception as _ie:
            logger.warning(f"[natives-idle] {label} build err: "
                           f"{_ie!r}")
            continue
        for _lbl, _auid, _pkt in _ents:
            try:
                await write_framed(w, _pkt)
            except Exception as _we:
                logger.debug(f"[natives-idle] {label} write err: {_we!r}")
                return


def start_natives_idle_ticker(writer, _conn_label, conn, *,
                              _conn_tasks) -> None:
    _nat_idle_sec = 0.5
    _conn_tasks.append(asyncio.create_task(
        _natives_idle_ticker(writer, _conn_label, conn,
                             _nat_idle_sec=_nat_idle_sec)))
    logger.info(f'[scene]   -> {_conn_label} natives idle ticker started (every {_nat_idle_sec:.2f}s.')


async def _story_npc_ticker(w, label, *,
                            _npc_sec,
                            live_avatars):
    while True:
        await asyncio.sleep(_npc_sec)
        if w.is_closing():
            return
        try:
            _pkts = _npc.tick_packets(live_avatars)
        except Exception as _te:
            logger.warning(f"[story-npc] {label} tick err: {_te!r}")
            continue
        for _pkt in _pkts:
            try:
                await write_framed(w, _pkt)
            except Exception as _we:
                logger.debug(f"[story-npc] {label} write err: {_we!r}")
                return


def start_story_npc_ticker(writer, _conn_label, *, _conn_tasks,
                           live_avatars) -> None:
    _npc_sec = 0.25
    _conn_tasks.append(asyncio.create_task(
        _story_npc_ticker(writer, _conn_label, _npc_sec=_npc_sec,
                          live_avatars=live_avatars)))
    logger.info(f"[scene]   -> {_conn_label} story-NPC ticker "
                f"started (every {_npc_sec:.2f}s)")


async def _corpse_sweeper(period, *,
                          _DYNAMIC_SCENE_AUIDS):
    while True:
        await asyncio.sleep(period)
        try:
            gone = _sweep_dmg.sweep_corpses()
        except Exception as _sx:
            logger.error(f"[corpse-sweep] err: {_sx!r}")
            continue
        for _d in gone:
            _DYNAMIC_SCENE_AUIDS.discard(_d.auid)
            try:
                _purge_story_npc_state(_d.auid)
            except Exception as _psx:
                logger.error(f"[corpse-sweep] story purge err: "
                             f"{_psx!r}")
            logger.info(f"[corpse-sweep] removed {_d.kind} "
                        f"0x{_d.auid:08x} ({_d.name!r}) after "
                        f"{_d.corpse_age_ms() // 1000}s"
                        + ("" if _d.looted
                           else " -- never skinned"))


def start_corpse_sweeper(_conn_label, *, _conn_tasks,
                         _DYNAMIC_SCENE_AUIDS) -> None:
    if _sweep_dmg.corpse_despawn_ms() > 0:
        _sweep_every = max(
            5.0, _sweep_dmg.corpse_despawn_ms() / 4000.0)
        _conn_tasks.append(asyncio.create_task(
            _corpse_sweeper(_sweep_every,
                            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)))
        logger.info(f'[scene]   -> {_conn_label} corpse sweeper started (every {_sweep_every:.0f}s, bodies last {_sweep_dmg.corpse_despawn_ms() // 1000}s.')


async def _forced_close(w, delay, label):
    try:
        await asyncio.sleep(delay)
        if not w.is_closing():
            logger.info(f'[scene]   {label}: one-shot forced close -> triggering scene-thread respawn (this is what unblocks the UI.')
            w.close()
            try:
                await w.wait_closed()
            except Exception as _wc:
                logger.debug(f"[scene]   {label}: wait_closed: {_wc!r}")
        else:
            logger.info(f"[scene] {label}: forced-close skipped. Socket already closing")
    except Exception as _fe:
        logger.error(f"[scene]   {label}: forced-close error: {_fe!r}")


def start_forced_close(writer, _conn_label, *, _conn_tasks) -> None:
    _hzca_delay = 0.25
    _conn_tasks.append(asyncio.create_task(
        _forced_close(writer, _hzca_delay, _conn_label)))
    logger.info(f"[scene]   {_conn_label}: scheduled one-shot forced "
                f"close in {_hzca_delay*1000:.0f}ms "
                f"(scene-thread respawn -> UI unblock)")
