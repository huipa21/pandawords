DEFINE TABLE OVERWRITE includes TYPE RELATION IN project OUT lemma | lexeme | sense | sentence | passage ENFORCED SCHEMAFULL;
DEFINE INDEX IF NOT EXISTS has_lexeme_tree_lookup ON has_lexeme FIELDS in, owner, out;
DEFINE INDEX IF NOT EXISTS has_sense_tree_lookup ON has_sense FIELDS in, owner, out;
