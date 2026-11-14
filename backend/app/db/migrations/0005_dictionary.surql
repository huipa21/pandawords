DEFINE TABLE IF NOT EXISTS lemma SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS text ON lemma TYPE string;
DEFINE FIELD IF NOT EXISTS lang ON lemma TYPE string;
DEFINE FIELD IF NOT EXISTS kind ON lemma TYPE 'word' | 'phrase';
DEFINE FIELD IF NOT EXISTS freq_zipf ON lemma TYPE number;
DEFINE FIELD IF NOT EXISTS cefr ON lemma TYPE option<string>;
DEFINE FIELD IF NOT EXISTS exam_tags ON lemma TYPE array<string>;
DEFINE FIELD IF NOT EXISTS source ON lemma TYPE string;
DEFINE FIELD IF NOT EXISTS owner ON lemma TYPE option<record<user>>;
DEFINE INDEX IF NOT EXISTS lemma_lang_text ON lemma FIELDS lang, text UNIQUE;

DEFINE TABLE IF NOT EXISTS lexeme SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS pos ON lexeme TYPE string;
DEFINE FIELD IF NOT EXISTS etymology_no ON lexeme TYPE int;
DEFINE FIELD IF NOT EXISTS etymology_text ON lexeme TYPE option<string>;
DEFINE FIELD IF NOT EXISTS forms ON lexeme TYPE array<object>;
DEFINE FIELD IF NOT EXISTS forms.*.form ON lexeme TYPE string;
DEFINE FIELD IF NOT EXISTS forms.*.tags ON lexeme TYPE array<string>;
DEFINE FIELD IF NOT EXISTS pron ON lexeme TYPE array<object>;
DEFINE FIELD IF NOT EXISTS pron.*.accent ON lexeme TYPE 'US' | 'UK';
DEFINE FIELD IF NOT EXISTS pron.*.ipa ON lexeme TYPE string;
DEFINE FIELD IF NOT EXISTS pron.*.audio ON lexeme TYPE option<record<media>>;
DEFINE FIELD IF NOT EXISTS owner ON lexeme TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS sense SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS definition ON sense TYPE string;
DEFINE FIELD IF NOT EXISTS gloss ON sense TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS gloss.* ON sense TYPE string;
DEFINE FIELD IF NOT EXISTS register ON sense TYPE array<string>;
DEFINE FIELD IF NOT EXISTS domain ON sense TYPE array<string>;
DEFINE FIELD IF NOT EXISTS examples ON sense TYPE array<string>;
DEFINE FIELD IF NOT EXISTS rank ON sense TYPE int;
DEFINE FIELD IF NOT EXISTS common ON sense TYPE bool;
DEFINE FIELD IF NOT EXISTS source ON sense TYPE string;
DEFINE FIELD IF NOT EXISTS owner ON sense TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS morpheme SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS text ON morpheme TYPE string;
DEFINE FIELD IF NOT EXISTS type ON morpheme TYPE 'prefix' | 'root' | 'suffix' | 'infix';
DEFINE FIELD IF NOT EXISTS meaning ON morpheme TYPE option<string>;
DEFINE FIELD IF NOT EXISTS owner ON morpheme TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS tag SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS kind ON tag TYPE string;
DEFINE FIELD IF NOT EXISTS name ON tag TYPE string;
DEFINE FIELD IF NOT EXISTS owner ON tag TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS sentence SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS text ON sentence TYPE string;
DEFINE FIELD IF NOT EXISTS lang ON sentence TYPE string;
DEFINE FIELD IF NOT EXISTS translation ON sentence TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS translation.* ON sentence TYPE string;
DEFINE FIELD IF NOT EXISTS source ON sentence TYPE string;
DEFINE FIELD IF NOT EXISTS owner ON sentence TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS passage SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS title ON passage TYPE string;
DEFINE FIELD IF NOT EXISTS text ON passage TYPE string;
DEFINE FIELD IF NOT EXISTS lang ON passage TYPE string;
DEFINE FIELD IF NOT EXISTS source ON passage TYPE string;
DEFINE FIELD IF NOT EXISTS owner ON passage TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS has_lexeme TYPE RELATION IN lemma OUT lexeme ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON has_lexeme TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS has_sense TYPE RELATION IN lexeme OUT sense ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS rank ON has_sense TYPE int;
DEFINE FIELD IF NOT EXISTS owner ON has_sense TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS composed_of TYPE RELATION IN lexeme OUT morpheme ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS order ON composed_of TYPE int;
DEFINE FIELD IF NOT EXISTS owner ON composed_of TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS derives_to TYPE RELATION IN lexeme OUT lexeme ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS via ON derives_to TYPE option<string>;
DEFINE FIELD IF NOT EXISTS owner ON derives_to TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS relates_to TYPE RELATION IN sense OUT sense ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS type ON relates_to TYPE
    'synonym' | 'antonym' | 'hypernym' | 'hyponym' | 'confusable' | 'collocation' | 'default';
DEFINE FIELD IF NOT EXISTS source ON relates_to TYPE string;
DEFINE FIELD IF NOT EXISTS owner ON relates_to TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS member_of TYPE RELATION IN sense | morpheme | tag OUT tag ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS owner ON member_of TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS contains TYPE RELATION IN lemma OUT lexeme ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS position ON contains TYPE int;
DEFINE FIELD IF NOT EXISTS owner ON contains TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS used_in TYPE RELATION IN sense OUT lemma | sentence | passage ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS span ON used_in TYPE option<array<int, 2>>;
DEFINE FIELD IF NOT EXISTS owner ON used_in TYPE option<record<user>>;

DEFINE TABLE IF NOT EXISTS part_of TYPE RELATION IN sentence OUT passage ENFORCED SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS order ON part_of TYPE int;
DEFINE FIELD IF NOT EXISTS owner ON part_of TYPE option<record<user>>;
