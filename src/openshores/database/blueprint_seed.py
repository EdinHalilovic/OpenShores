
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import struct
from datetime import datetime, timezone

import asyncpg

from openshores.core.config import Config
from openshores.core.logging import configure, get_logger
from openshores.database import pool as _pool
from openshores.database.migrations.runner import init_db
from openshores.database.repositories.blueprint import (blueprint_count,
                                                        upsert_blueprint)

logger = get_logger(__name__)

BLUEPRINT_SEED_DIR = "blueprints"


def _design_id(doc: dict, design_blob: bytes) -> int:
    did = int(doc.get("design_id", 0)) & 0xFFFFFFFF
    if not did and len(design_blob) >= 6:
        did = struct.unpack_from(">I", design_blob, 2)[0]
    return did


def _blob(doc: dict, key: str) -> bytes | None:
    raw = doc.get(key) or ""
    return bytes.fromhex(raw) if raw else None


async def import_blueprint_dir(conn: asyncpg.Connection,
                               directory: str = BLUEPRINT_SEED_DIR) -> dict:
    imported, skipped, ids = 0, 0, []
    for path in sorted(glob.glob(os.path.join(directory, "*.blueprint.json"))):
        stem = os.path.basename(path).split(".")[0]
        try:
            with open(path, "r") as fh:
                doc = json.load(fh)
            design_blob = _blob(doc, "design_blob_hex")
            if not design_blob:
                logger.warning("Blueprint seed %s carries no design blob; "
                               "skipped.", path)
                skipped += 1
                continue
            design_id = _design_id(doc, design_blob)
            if not design_id:
                logger.warning('Blueprint seed %s has no design id, in the JSON or in the blob header.', path)
                skipped += 1
                continue
            published_at = datetime.fromtimestamp(os.path.getmtime(path),
                                                  tz=timezone.utc)
        except Exception as exc:
            logger.warning("Blueprint seed %s did not load; skipped. %r",
                           path, exc)
            skipped += 1
            continue
        await upsert_blueprint(
            conn,
            design_id=design_id,
            name=doc.get("name", ""),
            stem=stem,
            soh_version=int(doc.get("soh_version", 0)),
            blueprint_type=int(doc.get("blueprint_type", 0)),
            design_state=int(doc.get("design_state", 1)),
            construction_process_id=int(doc.get("construction_process_id", 0)),
            design_material=int(doc.get("design_material", 0)),
            design_blob=design_blob,
            file_blob=_blob(doc, "file_blob_hex"),
            report_bytes=_blob(doc, "report_bytes_hex"),
            construction_blob=_blob(doc, "construction_blob_hex"),
            owner_auid=None,
            published_at=published_at)
        imported += 1
        ids.append(design_id)
        logger.info("Blueprint %r (design 0x%08x) imported from %s.",
                    doc.get("name", ""), design_id, path)
    logger.info("Blueprint import from %s: %d imported, %d skipped.",
                directory, imported, skipped)
    return {"imported": imported, "skipped": skipped, "design_ids": ids}


SEED_CANDIDATES = (BLUEPRINT_SEED_DIR, "_legacy_snapshot/recon/blueprints")


async def seed_if_empty(conn: asyncpg.Connection,
                        candidates: tuple[str, ...] = SEED_CANDIDATES) -> dict:
    if await blueprint_count(conn):
        return {"imported": 0, "skipped": 0, "design_ids": []}
    for directory in candidates:
        if glob.glob(os.path.join(directory, "*.blueprint.json")):
            return await import_blueprint_dir(conn, directory)
    logger.info('No blueprints to seed: looked in %s.',
                ", ".join(candidates))
    return {"imported": 0, "skipped": 0, "design_ids": []}


async def _run(directory: str, database_url: str | None) -> dict:
    url = database_url or Config.load().deployment.database_url
    pool = await _pool.connect(url)
    try:
        async with pool.acquire() as conn:
            await init_db(conn)
            return await import_blueprint_dir(conn, directory)
    finally:
        await _pool.close_path(url)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Import converter .blueprint.json output into hz_blueprint.")
    ap.add_argument("--dir", default=BLUEPRINT_SEED_DIR,
                    help="directory of *.blueprint.json converter output")
    ap.add_argument("--database-url", default=None,
                    help="override the deployment's database_url")
    args = ap.parse_args(argv)
    configure()
    asyncio.run(_run(args.dir, args.database_url))


if __name__ == "__main__":
    main()
