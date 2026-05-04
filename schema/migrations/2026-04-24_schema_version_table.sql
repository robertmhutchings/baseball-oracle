-- =============================================================
-- Phase 2 Step 3 prep: retro.schema_version history table
--
-- Append-only history of schema migrations. Read by ingest_full.py
-- at startup to detect schema drift; if checkpoint's recorded
-- schema_version doesn't match the latest row here, ingest refuses
-- to resume (per Step 3 design §4 sanity guards).
--
-- Version format: 'phase<N>-YYYY-MM-DD'. Bumped on each schema
-- migration. Initial row records the date of the last actual
-- schema change (Phase 2 Step 2 widening, applied 2026-04-24).
--
-- Read pattern (current version):
--   SELECT version FROM retro.schema_version
--   ORDER BY applied_at DESC LIMIT 1;
--
-- Future migrations: pure INSERT (no DELETE / no UPDATE).
--   INSERT INTO retro.schema_version (version, notes)
--   VALUES ('phase<N>-YYYY-MM-DD', '<description>');
--
-- 'version' is PRIMARY KEY so the same version string can't be
-- inserted twice by accident. 'applied_at' provides the implicit
-- time ordering used by the read pattern above.
-- =============================================================

BEGIN;

CREATE TABLE retro.schema_version (
    version     VARCHAR(32)  PRIMARY KEY,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    notes       TEXT
);

INSERT INTO retro.schema_version (version, notes) VALUES (
    'phase2-2026-04-24',
    'Phase 2 Step 2 widening: games.starttime VARCHAR(20), plays.pitch_count VARCHAR(8), teamstats.start_l1..l9/start_f1..f10 VARCHAR(10).'
);

COMMIT;
