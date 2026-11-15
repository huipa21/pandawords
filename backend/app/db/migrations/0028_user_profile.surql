DEFINE FIELD IF NOT EXISTS email ON user TYPE string DEFAULT '';
DEFINE FIELD IF NOT EXISTS full_name ON user TYPE string DEFAULT '';
DEFINE FIELD IF NOT EXISTS avatar ON user TYPE string DEFAULT '';
UPDATE user SET
    email = IF email = NONE THEN '' ELSE email END,
    full_name = IF full_name = NONE THEN '' ELSE full_name END,
    avatar = IF avatar = NONE THEN '' ELSE avatar END
WHERE email = NONE OR full_name = NONE OR avatar = NONE;
