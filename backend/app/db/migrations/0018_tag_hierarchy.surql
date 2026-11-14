DEFINE FIELD IF NOT EXISTS tag_revision ON user TYPE int DEFAULT 0;
UPDATE user SET tag_revision = 0 WHERE tag_revision = NONE;
DEFINE INDEX IF NOT EXISTS tag_owner ON tag FIELDS owner;
DEFINE INDEX IF NOT EXISTS member_owner_in ON member_of FIELDS owner, in;
DEFINE INDEX IF NOT EXISTS member_owner_out ON member_of FIELDS owner, out;
