CREATE TABLE IF NOT EXISTS "hz_blueprint" (

    "design_id"                      BIGINT PRIMARY KEY,

    "name"                           TEXT NOT NULL,

    "stem"                           TEXT NOT NULL,

    "soh_version"                    INTEGER NOT NULL,
    "blueprint_type"                 INTEGER NOT NULL,

    "design_state"                   INTEGER NOT NULL DEFAULT 1,

    "construction_process_id"        BIGINT NOT NULL DEFAULT 0,

    "design_material"                INTEGER NOT NULL DEFAULT 0,

    "design_blob"                    BYTEA NOT NULL,

    "file_blob"                      BYTEA,

    "report_bytes"                   BYTEA,

    "construction_blob"              BYTEA,

    "owner_auid"                     BIGINT,

    "published_at"                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS "ix_hz_blueprint_owner" ON "hz_blueprint" ("owner_auid");
