-- Three schemas, three owners in a real company:
--   legends     the figures database          (read by figures-db-mcp)
--   halloffame  the private app's own data     (read/written ONLY by hall-of-fame-api)
--   audit       append-only audit trail        (written by every MCP server)
-- They share one Postgres here to keep the stack small; each is reached through its own role.
--
-- The database repeats the rules the code already checks (slug format, lengths, allowed values).
-- Code can have a bug or be bypassed; a constraint cannot, so bad data fails here, loudly, at
-- insert time instead of surfacing later as a wrong answer from the model.
--
-- One transaction: if any statement fails, nothing is created. Without it a failed first start
-- leaves a half-built schema, and Postgres never re-runs init scripts on a non-empty volume.

BEGIN;

CREATE SCHEMA legends;
CREATE SCHEMA halloffame;
CREATE SCHEMA audit;

-- legends ------------------------------------------------------------------------------
-- Slugs match the tools' input pattern ^[a-z0-9-]{2,60}$; years match the tools' bounds.

CREATE TABLE legends.figures (
    id          int  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]{2,60}$'),
    name        text NOT NULL,
    born        int  NOT NULL CHECK (born BETWEEN 1700 AND 2100),
    died        int  CHECK (died BETWEEN 1700 AND 2100),
    country     text NOT NULL,
    known_for   text NOT NULL,
    bio         text NOT NULL,
    CHECK (died IS NULL OR died >= born)
);

CREATE TABLE legends.organizations (
    id          int  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]{2,60}$'),
    name        text NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('company', 'lab', 'university', 'nonprofit')),
    founded     int  NOT NULL CHECK (founded BETWEEN 1700 AND 2100),
    location    text NOT NULL
);

-- One row per stint: a person can leave an organisation and come back in another role
-- (Steve Jobs co-founded Apple in 1976 and returned as CEO in 1997).
CREATE TABLE legends.affiliations (
    figure_id        int  NOT NULL REFERENCES legends.figures (id),
    organization_id  int  NOT NULL REFERENCES legends.organizations (id),
    role             text NOT NULL,
    from_year        int  NOT NULL CHECK (from_year BETWEEN 1700 AND 2100),
    PRIMARY KEY (figure_id, organization_id, from_year)
);

CREATE TABLE legends.products (
    id               int  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug             text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]{2,60}$'),
    name             text NOT NULL,
    year             int  NOT NULL CHECK (year BETWEEN 1700 AND 2100),
    category         text NOT NULL CHECK (category IN (
                         'algorithm', 'chip', 'computer', 'dataset', 'device', 'film',
                         'language', 'machine', 'paper', 'platform', 'software')),
    organization_id  int  REFERENCES legends.organizations (id),
    lead_figure_id   int  REFERENCES legends.figures (id),
    description      text NOT NULL
);

CREATE TABLE legends.milestones (
    id          int  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    figure_id   int  NOT NULL REFERENCES legends.figures (id),
    year        int  NOT NULL CHECK (year BETWEEN 1700 AND 2100),
    title       text NOT NULL
);

-- An index on every foreign key that a query joins or filters on.
CREATE INDEX ON legends.affiliations (organization_id);
CREATE INDEX ON legends.products (lead_figure_id);
CREATE INDEX ON legends.products (organization_id);
CREATE INDEX ON legends.milestones (figure_id, year);

-- halloffame (owned by the private app) --------------------------------------------------
-- Every limit below mirrors apps/hall-of-fame-api: models.py (lengths), auth.py (owner =
-- username pattern) and app.py (Idempotency-Key header pattern).
-- Idempotency keys are unique PER OWNER: a key is chosen by the caller, so one user's key must
-- never block (or reveal) another user's request. A key always comes with the SHA-256 of the
-- request it belongs to; store.py compares that hash on every retry.

CREATE TABLE halloffame.collections (
    id               int  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner            text NOT NULL CHECK (owner ~ '^[a-z0-9_-]{2,40}$'),
    name             text NOT NULL CHECK (char_length(name) BETWEEN 2 AND 80),
    description      text NOT NULL DEFAULT '' CHECK (char_length(description) <= 500),
    created_at       timestamptz NOT NULL DEFAULT now(),
    idempotency_key  text CHECK (idempotency_key ~ '^[A-Za-z0-9_-]{8,64}$'),
    request_sha256   text CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    UNIQUE (owner, name),
    UNIQUE (owner, idempotency_key),
    CHECK ((idempotency_key IS NULL) = (request_sha256 IS NULL))
);

CREATE TABLE halloffame.collection_items (
    collection_id  int  NOT NULL REFERENCES halloffame.collections (id) ON DELETE CASCADE,
    figure_slug    text NOT NULL CHECK (figure_slug ~ '^[a-z0-9-]{2,60}$'),  -- loose reference:
    added_at       timestamptz NOT NULL DEFAULT now(),                       -- another system
    PRIMARY KEY (collection_id, figure_slug)                                 -- owns figures
);

CREATE TABLE halloffame.notes (
    id               int  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner            text NOT NULL CHECK (owner ~ '^[a-z0-9_-]{2,40}$'),
    figure_slug      text NOT NULL CHECK (figure_slug ~ '^[a-z0-9-]{2,60}$'),
    body             text NOT NULL CHECK (char_length(body) BETWEEN 3 AND 2000),
    created_at       timestamptz NOT NULL DEFAULT now(),
    idempotency_key  text CHECK (idempotency_key ~ '^[A-Za-z0-9_-]{8,64}$'),
    request_sha256   text CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    UNIQUE (owner, idempotency_key),
    CHECK ((idempotency_key IS NULL) = (request_sha256 IS NULL))
);

CREATE INDEX ON halloffame.notes (owner, figure_slug);

-- audit ----------------------------------------------------------------------------------
-- outcome values are the Outcome type in packages/mcp-kit/src/mcp_kit/audit.py. A row that
-- breaks a rule here is rejected, but it is never silently lost: the same event also goes to
-- the log sink, and the McpAuditWriteFailing alert fires (infra/prometheus/alert-rules.yml).

CREATE TABLE audit.events (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    server          text NOT NULL,
    correlation_id  text NOT NULL,
    subject         text NOT NULL,
    client_id       text NOT NULL,
    operation       text NOT NULL,
    args_sha256     text NOT NULL CHECK (args_sha256 ~ '^[0-9a-f]{64}$'),
    outcome         text NOT NULL CHECK (outcome IN ('ok', 'denied', 'error', 'crash')),
    duration_ms     int  NOT NULL CHECK (duration_ms >= 0),
    error           text CHECK (char_length(error) <= 500)
);

-- The model only ever sees "reference <correlation_id>"; this is how you find the full record.
CREATE INDEX ON audit.events (correlation_id);
-- "What did this user do, and when?"
CREATE INDEX ON audit.events (subject, occurred_at);

-- Append-only for everyone, not just audit_writer: grants already stop the services, and this
-- trigger also stops an admin's accidental UPDATE, DELETE or TRUNCATE. (A superuser can still
-- disable triggers on purpose; that leaves its own trace in the server log.)
CREATE FUNCTION audit.reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit.events is append-only (% is not allowed)', TG_OP;
END;
$$;

CREATE TRIGGER events_no_update_delete BEFORE UPDATE OR DELETE ON audit.events
    FOR EACH ROW EXECUTE FUNCTION audit.reject_change();
CREATE TRIGGER events_no_truncate BEFORE TRUNCATE ON audit.events
    FOR EACH STATEMENT EXECUTE FUNCTION audit.reject_change();

COMMIT;
