-- Least privilege: one login role per consumer, each able to do only its job.
-- Passwords come from the container environment (see infra/docker-compose.yml).

\getenv figures_reader_password FIGURES_READER_PASSWORD
\getenv halloffame_app_password HALLOFFAME_APP_PASSWORD
\getenv audit_writer_password AUDIT_WRITER_PASSWORD

-- figures-db-mcp: read the legends schema, nothing else.
CREATE ROLE figures_reader LOGIN PASSWORD :'figures_reader_password';
GRANT USAGE ON SCHEMA legends TO figures_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA legends TO figures_reader;
ALTER ROLE figures_reader SET default_transaction_read_only = on;

-- hall-of-fame-api: owns its data. The MCP server never gets this role; it calls the API.
CREATE ROLE halloffame_app LOGIN PASSWORD :'halloffame_app_password';
GRANT USAGE ON SCHEMA halloffame TO halloffame_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA halloffame TO halloffame_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA halloffame TO halloffame_app;

-- every MCP server: append to the audit trail, never read, change or delete it.
CREATE ROLE audit_writer LOGIN PASSWORD :'audit_writer_password';
GRANT USAGE ON SCHEMA audit TO audit_writer;
GRANT INSERT ON audit.events TO audit_writer;
GRANT USAGE ON SEQUENCE audit.events_id_seq TO audit_writer;
