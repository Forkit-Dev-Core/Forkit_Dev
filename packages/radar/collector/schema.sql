-- Explicit operator migration. Separate from Core/Registry identity tables.
BEGIN;
CREATE SCHEMA IF NOT EXISTS radar_metrics;
CREATE TABLE IF NOT EXISTS radar_metrics.surfaces (
  surface_hash char(64) PRIMARY KEY,
  credential_hash char(64) NOT NULL,
  sequence bigint NOT NULL CHECK (sequence >= 0 AND sequence <= 1000000000),
  payload jsonb,
  payload_digest char(64),
  updated_at timestamptz NOT NULL,
  withdrawn boolean NOT NULL DEFAULT false,
  CHECK ((payload IS NULL) = (payload_digest IS NULL)),
  CHECK (NOT withdrawn OR payload IS NULL)
);
CREATE TABLE IF NOT EXISTS radar_metrics.rate_limits (
  key_hash char(64) NOT NULL,
  hour timestamptz NOT NULL,
  hits integer NOT NULL CHECK(hits > 0),
  PRIMARY KEY(key_hash, hour)
);
COMMIT;

