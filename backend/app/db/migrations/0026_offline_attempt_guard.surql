DEFINE TABLE IF NOT EXISTS offline_attempt_guard SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON offline_attempt_guard TYPE record<user> ASSERT $value = record::id($this.id)[0];
DEFINE FIELD IF NOT EXISTS id ON offline_attempt_guard ASSERT $value = type::record('offline_attempt_guard', [$this.owner]);
DEFINE FIELD IF NOT EXISTS version ON offline_attempt_guard TYPE int DEFAULT 0;
DEFINE INDEX IF NOT EXISTS offline_attempt_guard_owner ON offline_attempt_guard FIELDS owner UNIQUE;
