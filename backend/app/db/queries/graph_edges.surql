SELECT * FROM has_lexeme, has_sense, composed_of, derives_to, relates_to,
member_of, contains, used_in, part_of
WHERE record::tb(id) IN $relations
AND (owner = NONE OR owner = $user)
AND (in.owner = NONE OR in.owner = $user)
AND (out.owner = NONE OR out.owner = $user)
AND in IN $authorized AND out IN $authorized
AND (($induced AND in IN $frontier AND out IN $frontier) OR
($induced = false AND (($direction != 'incoming' AND in IN $frontier) OR
($direction != 'outgoing' AND out IN $frontier))))
LIMIT $limit;
