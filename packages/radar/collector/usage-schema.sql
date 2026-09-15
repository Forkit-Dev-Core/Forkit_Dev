-- Additive: no Core, account, legacy Footprints or manual-report rows migrate.
BEGIN;
CREATE SCHEMA IF NOT EXISTS radar_metrics;
CREATE TABLE IF NOT EXISTS radar_metrics.installations (
  surface_hash char(64) PRIMARY KEY,
  credential_hash char(64) NOT NULL,
  sequence bigint NOT NULL CHECK(sequence >= 0 AND sequence <= 1000000000),
  payload jsonb,
  payload_digest char(64),
  updated_at timestamptz NOT NULL,
  withdrawn boolean NOT NULL DEFAULT false,
  CHECK ((payload IS NULL) = (payload_digest IS NULL)),
  CHECK (NOT withdrawn OR payload IS NULL)
);
CREATE INDEX IF NOT EXISTS installations_updated_at ON radar_metrics.installations(updated_at);
COMMIT;
