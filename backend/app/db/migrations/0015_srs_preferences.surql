DEFINE FIELD IF NOT EXISTS prefs.desired_retention ON user TYPE float DEFAULT 0.9 ASSERT $value > 0 AND $value < 1;
UPDATE user SET prefs.desired_retention = 0.9 WHERE prefs.desired_retention = NONE;
DEFINE FIELD IF NOT EXISTS srs_revision ON project TYPE int DEFAULT 0;
UPDATE project SET srs_revision = 0 WHERE srs_revision = NONE;

DEFINE FIELD IF NOT EXISTS request_fingerprint ON review_log TYPE option<string>;
DEFINE FIELD IF NOT EXISTS receipt ON review_log TYPE option<object> FLEXIBLE;
