-- The runner creates the history fields/index before applying any migrations.
-- Application tables are introduced by later forward-only migrations.
DEFINE TABLE IF NOT EXISTS _migration SCHEMAFULL;
