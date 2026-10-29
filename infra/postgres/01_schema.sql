-- Three schemas, three owners in a real company:
--   legends     the figures database          (read by figures-db-mcp)
--   halloffame  the private app's own data     (read/written ONLY by hall-of-fame-api)
--   audit       append-only audit trail        (written by every MCP server)
-- They share one Postgres here to keep the stack small; each is reached through its own role.

CREATE SCHEMA legends;
CREATE SCHEMA halloffame;
CREATE SCHEMA audit;

-- legends ------------------------------------------------------------------------------

CREATE TABLE legends.figures (
    id          serial PRIMARY KEY,
    slug        text NOT NULL UNIQUE,
    name        text NOT NULL,
    born        int  NOT NULL,
    died        int,
    country     text NOT NULL,
    known_for   text NOT NULL,
    bio         text NOT NULL
);

CREATE TABLE legends.organizations (
    id          serial PRIMARY KEY,
    slug        text NOT NULL UNIQUE,
    name        text NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('company', 'lab', 'university', 'nonprofit')),
    founded     int  NOT NULL,
    location    text NOT NULL
);

CREATE TABLE legends.affiliations (
    figure_id        int  NOT NULL REFERENCES legends.figures (id),
    organization_id  int  NOT NULL REFERENCES legends.organizations (id),
    role             text NOT NULL,
    from_year        int  NOT NULL,
    PRIMARY KEY (figure_id, organization_id)
);

CREATE TABLE legends.products (
    id               serial PRIMARY KEY,
    slug             text NOT NULL UNIQUE,
    name             text NOT NULL,
    year             int  NOT NULL,
    category         text NOT NULL,
    organization_id  int  REFERENCES legends.organizations (id),
    lead_figure_id   int  REFERENCES legends.figures (id),
    description      text NOT NULL
);

CREATE TABLE legends.milestones (
    id          serial PRIMARY KEY,
    figure_id   int  NOT NULL REFERENCES legends.figures (id),
    year        int  NOT NULL,
    title       text NOT NULL
);

CREATE INDEX ON legends.products (lead_figure_id);
CREATE INDEX ON legends.milestones (figure_id, year);

-- halloffame (owned by the private app) --------------------------------------------------

CREATE TABLE halloffame.collections (
    id               serial PRIMARY KEY,
    owner            text NOT NULL,
    name             text NOT NULL,
    description      text NOT NULL DEFAULT '',
    created_at       timestamptz NOT NULL DEFAULT now(),
    idempotency_key  text UNIQUE,
    request_sha256   text,
    UNIQUE (owner, name)
);

CREATE TABLE halloffame.collection_items (
    collection_id  int  NOT NULL REFERENCES halloffame.collections (id),
    figure_slug    text NOT NULL,  -- loose reference: another system owns figures
    added_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_id, figure_slug)
);

CREATE TABLE halloffame.notes (
    id               serial PRIMARY KEY,
    owner            text NOT NULL,
    figure_slug      text NOT NULL,
    body             text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    idempotency_key  text UNIQUE,
    request_sha256   text
);

CREATE INDEX ON halloffame.notes (owner, figure_slug);

-- audit ----------------------------------------------------------------------------------

CREATE TABLE audit.events (
    id              bigserial PRIMARY KEY,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    server          text NOT NULL,
    correlation_id  text NOT NULL,
    subject         text NOT NULL,
    client_id       text NOT NULL,
    operation       text NOT NULL,
    args_sha256     text NOT NULL,
    outcome         text NOT NULL,
    duration_ms     int  NOT NULL,
    error           text
);
