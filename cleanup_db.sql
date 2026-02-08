-- Drop cascading all tables and schemas (except public)
DROP SCHEMA IF EXISTS education CASCADE;
DROP SCHEMA IF EXISTS scales CASCADE;
DROP SCHEMA IF EXISTS vitals CASCADE;
DROP SCHEMA IF EXISTS users CASCADE;

-- Reset alembic version table
DELETE FROM alembic_version;
