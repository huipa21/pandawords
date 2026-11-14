DEFINE TABLE IF NOT EXISTS admin_guard SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS version ON admin_guard TYPE int;
UPSERT admin_guard:singleton SET version = 0;
