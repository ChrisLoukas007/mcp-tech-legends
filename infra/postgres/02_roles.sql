-- Least privilege: one login role per consumer, each able to do only its job.
-- Passwords come from the container environment (see infra/docker-compose.yml).
-- Runs once, as the postgres superuser, when the data volume is empty.

\getenv figures_reader_password FIGURES_READER_PASSWORD
\getenv halloffame_app_password HALLOFFAME_APP_PASSWORD
\getenv audit_writer_password AUDIT_WRITER_PASSWORD

-- Start from nothing: by default PUBLIC (every role) may connect to any database, create
-- temporary tables and use the public schema. Take that away, then grant CONNECT per role.
REVOKE ALL ON DATABASE legends FROM PUBLIC;
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- figures-db-mcp: read the legends schema, nothing else.
CREATE ROLE figures_reader LOGIN CONNECTION LIMIT 20 PASSWORD :'figures_reader_password';
GRANT CONNECT ON DATABASE legends TO figures_reader;
GRANT USAGE ON SCHEMA legends TO figures_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA legends TO figures_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA legends GRANT SELECT ON TABLES TO figures_reader;
-- Defence in depth only: a session can turn this off; the SELECT-only grant is the real limit.
ALTER ROLE figures_reader SET default_transaction_read_only = on;

-- hall-of-fame-api: the only service that reads or writes this schema. It needs SELECT and
-- INSERT (writes are INSERT ... ON CONFLICT DO NOTHING); no UPDATE, DELETE or DDL. The tables
-- stay owned by postgres. The MCP server never gets this role; it calls the API.
CREATE ROLE halloffame_app LOGIN CONNECTION LIMIT 20 PASSWORD :'halloffame_app_password';
GRANT CONNECT ON DATABASE legends TO halloffame_app;
GRANT USAGE ON SCHEMA halloffame TO halloffame_app;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA halloffame TO halloffame_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA halloffame TO halloffame_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA halloffame GRANT SELECT, INSERT ON TABLES TO halloffame_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA halloffame GRANT USAGE ON SEQUENCES TO halloffame_app;

-- every MCP server: append to the audit trail, never read, change or delete it.
CREATE ROLE audit_writer LOGIN CONNECTION LIMIT 20 PASSWORD :'audit_writer_password';
GRANT CONNECT ON DATABASE legends TO audit_writer;
GRANT USAGE ON SCHEMA audit TO audit_writer;
GRANT INSERT ON audit.events TO audit_writer;
GRANT USAGE ON SEQUENCE audit.events_id_seq TO audit_writer;
