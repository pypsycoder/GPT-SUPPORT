-- List all schemas
SELECT schema_name 
FROM information_schema.schemata 
WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'public') 
ORDER BY schema_name;

-- List all tables with their schemas
SELECT table_schema, table_name 
FROM information_schema.tables 
WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'public') 
ORDER BY table_schema, table_name;

-- Count tables by schema
SELECT table_schema, COUNT(*) as table_count 
FROM information_schema.tables 
WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'public') 
GROUP BY table_schema 
ORDER BY table_schema;
