DEFINE TABLE IF NOT EXISTS llm_cache SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON llm_cache TYPE option<record<user>>;
DEFINE FIELD IF NOT EXISTS key ON llm_cache TYPE string;
DEFINE FIELD IF NOT EXISTS response_json ON llm_cache TYPE string;
DEFINE FIELD IF NOT EXISTS created_at ON llm_cache TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS llm_cache_owner_key ON llm_cache FIELDS owner, key UNIQUE;

DEFINE TABLE IF NOT EXISTS llm_budget SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON llm_budget TYPE record<user>;
DEFINE FIELD IF NOT EXISTS day ON llm_budget TYPE string;
DEFINE FIELD IF NOT EXISTS attempts ON llm_budget TYPE int ASSERT $value >= 0;
DEFINE INDEX IF NOT EXISTS llm_budget_owner_day ON llm_budget FIELDS owner, day UNIQUE;
