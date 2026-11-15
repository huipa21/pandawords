SELECT * FROM type::table($relation)
WHERE (owner = NONE OR owner = $user)
AND (in.owner = NONE OR in.owner = $user)
AND (out.owner = NONE OR out.owner = $user)
AND in IN $authorized AND out IN $authorized
AND (($induced AND in IN $frontier AND out IN $frontier) OR
($induced = false AND (($direction != 'incoming' AND in IN $frontier) OR
($direction != 'outgoing' AND out IN $frontier))))
LIMIT $limit;
