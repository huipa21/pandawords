DEFINE TABLE IF NOT EXISTS exercise_attempt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON exercise_attempt TYPE record<user>;
DEFINE FIELD IF NOT EXISTS project ON exercise_attempt TYPE record<project>;
DEFINE FIELD IF NOT EXISTS sense ON exercise_attempt TYPE record<sense>;
DEFINE FIELD IF NOT EXISTS status ON exercise_attempt TYPE 'open' | 'graded' | 'confirmed';
DEFINE FIELD IF NOT EXISTS issued_at ON exercise_attempt TYPE datetime;
DEFINE FIELD IF NOT EXISTS expires_at ON exercise_attempt TYPE datetime ASSERT $value > $this.issued_at;
DEFINE FIELD IF NOT EXISTS payload ON exercise_attempt TYPE string;
DEFINE INDEX IF NOT EXISTS exercise_attempt_owner_expiry ON exercise_attempt FIELDS owner, expires_at;
