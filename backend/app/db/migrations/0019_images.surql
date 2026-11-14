DEFINE TABLE IF NOT EXISTS image_request SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON image_request TYPE record<user>;
DEFINE FIELD IF NOT EXISTS target ON image_request TYPE record<sense>;
DEFINE FIELD IF NOT EXISTS fingerprint ON image_request TYPE string;
DEFINE FIELD IF NOT EXISTS source_identity ON image_request TYPE option<string>;
DEFINE FIELD IF NOT EXISTS media ON image_request TYPE option<record<media>>;
DEFINE INDEX IF NOT EXISTS image_request_owner ON image_request FIELDS owner, target;

DEFINE TABLE IF NOT EXISTS image_search SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON image_search TYPE record<user>;
DEFINE FIELD IF NOT EXISTS expires_at ON image_search TYPE datetime;
DEFINE FIELD IF NOT EXISTS data ON image_search TYPE string;
DEFINE INDEX IF NOT EXISTS image_search_owner ON image_search FIELDS owner, expires_at;

DEFINE TABLE IF NOT EXISTS image_rate SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON image_rate TYPE record<user>;
DEFINE FIELD IF NOT EXISTS until ON image_rate TYPE datetime;
DEFINE FIELD IF NOT EXISTS revision ON image_rate TYPE int DEFAULT 0;

DEFINE TABLE IF NOT EXISTS image_provider_rate SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS until ON image_provider_rate TYPE datetime;
DEFINE FIELD IF NOT EXISTS count ON image_provider_rate TYPE int DEFAULT 0;
