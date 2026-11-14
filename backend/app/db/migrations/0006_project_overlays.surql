DEFINE TABLE IF NOT EXISTS project SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON project TYPE record<user>;
DEFINE FIELD IF NOT EXISTS name ON project TYPE string;
DEFINE FIELD IF NOT EXISTS description ON project TYPE string;
DEFINE FIELD IF NOT EXISTS target_lang ON project TYPE string;
DEFINE FIELD IF NOT EXISTS source_lang ON project TYPE string;
DEFINE FIELD IF NOT EXISTS plan ON project TYPE object;
DEFINE FIELD IF NOT EXISTS plan.daily_new ON project TYPE int;
DEFINE FIELD IF NOT EXISTS plan.exam_date ON project TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS plan.review_cap ON project TYPE option<int>;
DEFINE FIELD IF NOT EXISTS created_at ON project TYPE datetime;
DEFINE INDEX IF NOT EXISTS project_owner ON project FIELDS owner;

DEFINE TABLE IF NOT EXISTS includes TYPE RELATION IN project OUT lemma | sense | sentence | passage ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON includes TYPE record<user>;
DEFINE FIELD IF NOT EXISTS hidden ON includes TYPE bool;
DEFINE FIELD IF NOT EXISTS added_at ON includes TYPE datetime;

DEFINE TABLE IF NOT EXISTS override SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON override TYPE record<user>;
DEFINE FIELD IF NOT EXISTS fields ON override TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS updated_at ON override TYPE datetime;

DEFINE TABLE IF NOT EXISTS note SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON note TYPE record<user>;
DEFINE FIELD IF NOT EXISTS target ON note TYPE record;
DEFINE FIELD IF NOT EXISTS kind ON note TYPE 'note' | 'mnemonic';
DEFINE FIELD IF NOT EXISTS text ON note TYPE string;
DEFINE INDEX IF NOT EXISTS note_owner_target ON note FIELDS owner, target;
