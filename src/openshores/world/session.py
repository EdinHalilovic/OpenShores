
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from openshores.core.config import Gameplay
from openshores.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Session:

    writer: Any
    peer: tuple
    peer_host: str
    conn_n: int
    conn_t0: float
    label: str = ""

    player_auid: int = 0
    player_auid_bytes: bytes = b""
    avatar_name: str = ""
    avatar_dna: bytes = b""
    is_primary: bool = True

    parent_world_auid: int = 0
    parent_world_auid_bytes: bytes = b""
    world_atom_auids: set = field(default_factory=set)

    augear: list = field(default_factory=list)

    conn_tasks: list = field(default_factory=list)

    scene_manifest_builder: Optional[Any] = None

    chat_writer: Any = None

    last_rx_t: Optional[float] = None
    last_rx_op: Optional[int] = None
    op_tally: dict = field(default_factory=dict)

    lookat_target_auid: int = 0
    lookat_since_ts: float = 0.0

    bootstrap_published: bool = False
    variant_b_handled: bool = False
    force_closed_once: bool = False

    dirty_position: bool = False
    last_position_xyz: tuple = (0.0, 0.0, 0.0)
    last_position_parent_world: int = 0
    last_position_flush_ts: float = 0.0

    dirty_bio: dict = field(default_factory=dict)
    last_bio_flush_ts: float = 0.0

    hot_state_flushes_total: int = 0
    hot_state_suppressed_total: int = 0

    def set_player_auid(self, auid: int | bytes) -> None:
        if isinstance(auid, (bytes, bytearray)):
            self.player_auid_bytes = bytes(auid[:4])
            self.player_auid = int.from_bytes(self.player_auid_bytes,
                                              "big") & 0xFFFFFFFF
        else:
            self.player_auid = int(auid) & 0xFFFFFFFF
            self.player_auid_bytes = self.player_auid.to_bytes(4, "big")

    def set_parent_world(self, auid: int | bytes) -> None:
        if isinstance(auid, (bytes, bytearray)):
            self.parent_world_auid_bytes = bytes(auid[:4])
            self.parent_world_auid = int.from_bytes(
                self.parent_world_auid_bytes, "big") & 0xFFFFFFFF
        else:
            self.parent_world_auid = int(auid) & 0xFFFFFFFF
            self.parent_world_auid_bytes = (
                self.parent_world_auid.to_bytes(4, "big"))

    def track_task(self, task) -> None:
        self.conn_tasks.append(task)
        return task

    def cancel_all_tasks(self) -> int:
        n = 0
        for t in self.conn_tasks:
            if not t.done():
                t.cancel()
                n += 1
        return n

    def mark_position_dirty(self, x: float, y: float, z: float,
                            parent_world: int = 0) -> None:
        self.last_position_xyz = (float(x), float(y), float(z))
        if parent_world:
            self.last_position_parent_world = int(parent_world) & 0xFFFFFFFF
        self.dirty_position = True

    def mark_bio_dirty(self, **fields) -> None:
        for k, v in fields.items():
            self.dirty_bio[k] = v

    def flush_to_queue(self, queue, force: bool = False) -> int:
        if self.player_auid == 0:
            return 0
        if queue is None or not queue.is_running():
            return 0
        submits = 0
        if self.dirty_position:
            x, y, z = self.last_position_xyz
            if self.last_position_parent_world:
                ok = queue.submit("update_person_position",
                                  self.player_auid, x, y, z,
                                  self.last_position_parent_world)
            else:
                ok = queue.submit("update_person_position",
                                  self.player_auid, x, y, z)
            if ok:
                self.dirty_position = False
                submits += 1
        if self.dirty_bio:
            snapshot = dict(self.dirty_bio)
            ok = queue.submit("update_person_state",
                              self.player_auid, **snapshot)
            if ok:
                for k in snapshot:
                    if self.dirty_bio.get(k) == snapshot[k]:
                        self.dirty_bio.pop(k, None)
                submits += 1
        if submits:
            self.hot_state_flushes_total += 1
        return submits

    def __repr__(self) -> str:
        return (f"Session(peer={self.peer}, "
                f"auid=0x{self.player_auid:08x}, "
                f"name={self.avatar_name!r}, "
                f"tasks={len(self.conn_tasks)})")


async def state_flush_ticker(session, writer, queue,
                             interval_s: float | None = None):
    try:
        if interval_s is None:
            interval_s = Gameplay().hot_state_flush_seconds
        interval_s = max(0.5, float(interval_s))
        while not writer.is_closing():
            await asyncio.sleep(interval_s)
            if writer.is_closing():
                break
            try:
                session.flush_to_queue(queue)
            except Exception as exc:
                logger.error('Hot-state flush failed for avatar 0x%08x: %r.', session.player_auid, exc)
    except asyncio.CancelledError:
        session.flush_to_queue(queue, force=True)
        raise


if __name__ == "__main__":  # pragma: no cover
    import time as _t

    from openshores.core.logging import configure

    configure("INFO")
    s = Session(
        writer=None,
        peer=("127.0.0.1", 60005),
        peer_host="127.0.0.1",
        conn_n=1,
        conn_t0=_t.monotonic(),
        label="c1",
    )
    s.set_player_auid(0x0005A3E5)
    s.set_parent_world(0x0005A66E)
    logger.info("%s", s)
    s.mark_position_dirty(1.0, 2.0, 3.0, parent_world=0x12345)
    s.mark_bio_dirty(hp=42, hunger=3)
    logger.info("Dirty pos: %s xyz: %s", s.dirty_position, s.last_position_xyz)
    logger.info("Dirty bio: %s", s.dirty_bio)
