

from __future__ import annotations

import asyncio
import contextlib as _ctxlib

from openshores.core import metrics as _server_metrics
from openshores.core.accounts import default_store
from openshores.core.config import Config
from openshores.core.heartbeat_watch import _loop_lag_watchdog
from openshores.core.logging import get_logger
from openshores.core.whereabouts import string_id as _wb_sid
from openshores.core.whereabouts import write_whereabouts_all
from openshores.database import journal as _persist_queue
from openshores.database import pool as _pool
from openshores.database.repositories.person import (cleanup_orphan_placeholders,
                                                     clear_all_online_flags)
from openshores.database.repositories.whereabouts import globe_name_for_person
from openshores.gameplay.gd_commodity_scan import _load_container_cids
from openshores.gameplay.vehicles.persistence import (
    ensure_schema as _veh_ensure_schema)
from openshores.gameplay.vehicles.spawn import (active_vehicle_count as
                                                _veh_active_count)
from openshores.gameplay.vehicles.spawn import hydrate_from_db as _veh_hydrate
from openshores.network.control import _control_start
from openshores.network.mail_server import handle_chatmail, handle_mail
from openshores.network.vehicle_terrain import (
    install_radial_terrain as _veh_install_radial_terrain)

logger = get_logger(__name__)


async def main(config: Config, *,
               handle_login,
               handle_scene,
               handle_chat,
               _pickup_speculation_loop,
               _restore_persisted_cities,
               _restore_persisted_buildings,
               _city_sim_manager,
               _city_development_loop,
               _mfg_environment_loop,
               _install_native_conversation_hooks,
               _install_dump_state_signal_handler,
               _udp_start,
               _get_starmap_blob,
               _SAVE,
               resolve_person_id,
               session_login_ms: dict,
               _live_avatars: dict,
               _DROPPED_ITEMS: dict,
               _AUGEAR_STATES: dict,
               _VEH_KEEPALIVE_TASKS: dict) -> None:
    host = config.deployment.bind_host
    pool = await _pool.connect(config.deployment.database_url)


    _load_container_cids()

    async with pool.acquire() as conn:
        await clear_all_online_flags(conn)
        _veh_schema_ok = await _veh_ensure_schema(conn)
        _veh_row_count = (await _veh_hydrate(conn=conn)
                          if _veh_schema_ok else -1)
        logger.info(f"[boot] a_Vehicle: schema={('ok' if _veh_schema_ok else 'failed')}, rows={_veh_row_count}, active={_veh_active_count()}")

    _veh_install_radial_terrain()

    login_server = await asyncio.start_server(
        handle_login, host, config.deployment.login_port)
    scene_server = await asyncio.start_server(
        handle_scene, host, config.deployment.scene_port)
    chat_server = await asyncio.start_server(
        lambda r, w: handle_chatmail(r, w, handle_chat=handle_chat,
                                     handle_mail=handle_mail),
        host, config.deployment.chat_port)
    mail_server = await asyncio.start_server(
        handle_mail, host, config.deployment.mail_port)
    ctl_server = await _control_start(
        control_port=config.deployment.control_port,
        live_avatars=_live_avatars, pool=pool)
    _install_native_conversation_hooks()
    await _udp_start()
    asyncio.create_task(_pickup_speculation_loop())
    asyncio.create_task(_restore_persisted_cities())
    asyncio.create_task(_restore_persisted_buildings())
    asyncio.create_task(_city_sim_manager())
    asyncio.create_task(_city_development_loop())
    asyncio.create_task(_loop_lag_watchdog())
    asyncio.create_task(_mfg_environment_loop())
    logger.info('[boot] vehicle server-side physics disabled.')
    logger.info("[boot] login  listening on %s:%d"
                % (host, config.deployment.login_port))
    logger.info("[boot] scene  listening on %s:%d"
                % (host, config.deployment.scene_port))
    logger.info("[boot] chat   listening on %s:%d"
                % (host, config.deployment.chat_port))
    logger.info("[boot] public host advertised to clients: "
                + str(config.deployment.public_host))
    _install_dump_state_signal_handler()

    _persist_queue.start_queue(pool, resolve_person_id, session_login_ms)

    _server_metrics.add_provider(
        "live_avatars_count",
        lambda: len(_live_avatars))
    _server_metrics.add_provider(
        "dropped_items_count",
        lambda: len(_DROPPED_ITEMS))
    _server_metrics.add_provider(
        "asyncio_tasks_running",
        lambda: sum(1 for t in asyncio.all_tasks()
                    if not t.done()))
    _server_metrics.add_provider(
        "augear_states_count",
        lambda: len(_AUGEAR_STATES))
    _server_metrics.add_provider(
        "veh_keepalive_tasks_count",
        lambda: len(_VEH_KEEPALIVE_TASKS))

    def _pq_depth():
        q = _persist_queue.get_queue()
        return q.depth() if q is not None else 0

    def _pq_committed():
        q = _persist_queue.get_queue()
        return q.committed_total if q is not None else 0

    def _pq_failed():
        q = _persist_queue.get_queue()
        return q.failed_total if q is not None else 0

    def _pq_batches():
        q = _persist_queue.get_queue()
        return q.batches_total if q is not None else 0

    def _pq_last_batch_size():
        q = _persist_queue.get_queue()
        return q.last_batch_size if q is not None else 0

    def _pq_last_batch_dur_ms():
        q = _persist_queue.get_queue()
        return (
            round(q.last_batch_dur_ms, 2)
            if q is not None else 0)

    _server_metrics.add_provider(
        "persist_queue_depth", _pq_depth)
    _server_metrics.add_provider(
        "persist_committed_total", _pq_committed)
    _server_metrics.add_provider(
        "persist_failed_total", _pq_failed)
    _server_metrics.add_provider(
        "persist_batches_total", _pq_batches)
    _server_metrics.add_provider(
        "persist_last_batch_size", _pq_last_batch_size)
    _server_metrics.add_provider(
        "persist_last_batch_dur_ms", _pq_last_batch_dur_ms)

    def _g2_flushes():
        try:
            return sum(
                e["session"].hot_state_flushes_total
                for e in _live_avatars.values()
                if isinstance(e, dict)
                and e.get("session") is not None)
        except Exception as exc:
            logger.debug("hot_state_flushes_total unavailable: %r", exc)
            return 0

    def _g2_suppressed():
        try:
            return sum(
                e["session"].hot_state_suppressed_total
                for e in _live_avatars.values()
                if isinstance(e, dict)
                and e.get("session") is not None)
        except Exception as exc:
            logger.debug("hot_state_suppressed_total unavailable: %r", exc)
            return 0

    _server_metrics.add_provider(
        "hot_state_flushes_total", _g2_flushes)
    _server_metrics.add_provider(
        "hot_state_suppressed_total", _g2_suppressed)
    _server_metrics.start_if_configured(config.deployment.metrics_port)

    async with pool.acquire() as conn:
        _orph_n = await cleanup_orphan_placeholders(conn, min_age_seconds=0)
    if _orph_n:
        logger.info(f"[boot]   PRE_INSERT orphan cleanup: removed "
                    f"{_orph_n} abandoned wizard placeholder(s)")

    logger.info("[boot] save source=%s  universe=%r  empire=%r  sector=%r  system=%r  star=%r  planet=%r  person=%r" % (
        _SAVE.source, _SAVE.universe_name, _SAVE.empire_name,
        _SAVE.sector_name, _SAVE.system_name, _SAVE.star_name,
        _SAVE.planet_name, _SAVE.person_name))

    if _SAVE.whereabouts_display:
        store = default_store()
        seeded = []
        skipped = []
        async with pool.acquire() as conn:
            for user in store.list_users():
                _avs = store.list_avatars(user) or []
                if not _avs:
                    skipped.append(user)
                    continue
                for _av in _avs:
                    try:
                        _aid = int(_av)
                    except (TypeError, ValueError):
                        continue
                    _name = await globe_name_for_person(conn, _aid)
                    _where = (f"On {_name}" if _name
                              else _SAVE.whereabouts_display)
                    n = write_whereabouts_all(
                        _wb_sid(_aid), _where, verbose=False)
                    if n > 0:
                        seeded.append(
                            (f"{user}/{_wb_sid(_aid)}", n, _where))
        if seeded:
            for user, n, where in seeded:
                logger.info("[boot] whereabouts seeded for %r "
                            "(%d reg base(s)) -> %r" % (user, n, where))
        if skipped:
            logger.info("[boot] whereabouts: skipped %d account(s) "
                        "with empty roster: %r" % (len(skipped), skipped))
        if not seeded and not skipped:
            logger.info("[boot] whereabouts: no accounts found; "
                        "skipped seeding")

    try:
        _sm_blob = _get_starmap_blob()
        logger.info("[boot] starmap ready: %d bytes (first 16B: %s)"
                    % (len(_sm_blob), _sm_blob[:16].hex()))
    except Exception as _sme:
        logger.error("[boot] starmap build failed: " + repr(_sme))

    async def _supervise(_name: str, _server):
        _fails = 0
        while True:
            try:
                await _server.serve_forever()
                logger.info(f"[supervisor] {_name} exited")
                return
            except asyncio.CancelledError:
                raise
            except Exception as _se:
                _fails += 1
                _backoff = min(30.0, 2.0 * _fails)
                logger.error(f"[supervisor] {_name} crashed: {_se!r} "
                             f"(fail #{_fails}); restarting in "
                             f"{_backoff:.1f}s")
                try:
                    _server_metrics.incr(
                        "supervisor_crashes", tag=_name)
                    _server_metrics.incr(
                        "exceptions_total",
                        tag=type(_se).__name__)
                except Exception as _mx:
                    logger.debug("Supervisor metrics not recorded: %r", _mx)
                await asyncio.sleep(_backoff)

    _servers = [("login", login_server), ("scene", scene_server),
                ("chat", chat_server)]
    _servers.append(("mail", mail_server))
    logger.info("[boot] mail   listening on %s:%d (capture mode)"
                % (host, config.deployment.mail_port))
    async with _ctxlib.AsyncExitStack() as _stk:
        for _n, _s in _servers:
            await _stk.enter_async_context(_s)
        await asyncio.gather(
            *[_supervise(_n, _s) for _n, _s in _servers],
            return_exceptions=True,
        )
