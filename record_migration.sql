-- Create alembic_version table and record current migration
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

-- Insert the current migration version
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('5e1f8a2c3b4d');
