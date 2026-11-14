DEFINE FIELD IF NOT EXISTS source ON morpheme TYPE option<string>;
DEFINE FIELD IF NOT EXISTS source ON composed_of TYPE option<string>;
DEFINE FIELD IF NOT EXISTS source ON member_of TYPE option<string>;
DEFINE INDEX IF NOT EXISTS composed_owner_in_order ON composed_of FIELDS owner, in, order;
