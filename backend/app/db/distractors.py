"""Bounded candidate discovery over the existing Phase 2 graph."""

import math
from typing import Any
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.record_ids import decode_rid, encode_rid
from app.db.auth import _atomic, _rows
from app.db.dictionary import TABLE_FIELDS, _merge, _record
from app.db.srs import user_record
from app.domain.distractors import DistractorPool, DistractorRecord
from app.domain.exercises import ExerciseContext

LIMIT = 64


async def candidate_pool(
    db: AsyncSurrealConnection, context: ExerciseContext
) -> DistractorPool | None:
    async def operation(txn: UUID) -> DistractorPool | None:
        user = user_record(context.owner)
        answer = decode_rid(context.sense_id, "sense")
        params: dict[str, Value] = {"user": user, "answer": answer, "limit": LIMIT + 1}
        answer_lemma = decode_rid(context.lemma.id, "lemma")
        answer_lexeme = decode_rid(context.lexeme.id, "lexeme")
        lemma = await _record(db, user, answer_lemma, txn)
        lexeme = await _record(db, user, answer_lexeme, txn)
        if lemma is None or lexeme is None:
            return None

        async def query(sql: str, **extra: Any) -> list[dict[str, Any]]:
            return await _rows(db, sql, {**params, **extra}, txn_id=txn)

        # Synonyms are never truncated: an oversized safety set fails closed.
        synonyms = await query(
            "SELECT id, in, out FROM relates_to WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND type = 'synonym' AND (in = $answer OR out = $answer) "
            "ORDER BY id LIMIT $limit;"
        )
        if len(synonyms) > LIMIT:
            return None
        excluded = {row["out"] if row["in"] == answer else row["in"] for row in synonyms}
        tiers: dict[RecordID, int] = {}
        for tier, kinds in ((0, ["concept", "domain"]), (1, ["morph_group"])):
            memberships = await query(
                "SELECT id, out FROM member_of WHERE (owner = NONE OR owner = $user) "
                "AND (in.owner = NONE OR in.owner = $user) "
                "AND (out.owner = NONE OR out.owner = $user) "
                "AND in = $answer AND out.kind IN $kinds ORDER BY id LIMIT $limit;",
                kinds=kinds,
            )
            tags = [row["out"] for row in memberships]
            rows = await query(
                "SELECT id, in FROM member_of WHERE (owner = NONE OR owner = $user) "
                "AND (in.owner = NONE OR in.owner = $user) "
                "AND (out.owner = NONE OR out.owner = $user) "
                "AND out IN $tags AND in != $answer ORDER BY id LIMIT $limit;",
                tags=tags[:LIMIT],
            )
            for row in rows[:LIMIT]:
                if row["in"].table_name == "sense":
                    tiers.setdefault(row["in"], tier)
        confusable = await query(
            "SELECT id, in, out FROM relates_to WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND type = 'confusable' AND (in = $answer OR out = $answer) "
            "ORDER BY id LIMIT $limit;"
        )
        for row in confusable[:LIMIT]:
            tiers.setdefault(row["out"] if row["in"] == answer else row["in"], 2)

        # Query base POS/frequency only as a discovery bound; effective values below
        # are authoritative. Unknown/zero frequency is rejected by the service.
        frequency = lemma.fields.get("freq_zipf")
        band = (
            math.floor(frequency)
            if isinstance(frequency, (int, float)) and math.isfinite(frequency) and frequency > 0
            else -1
        )
        fallback = await query(
            "SELECT id, out FROM has_lexeme WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND in.freq_zipf > 0 AND in.freq_zipf >= $band AND in.freq_zipf < $upper "
            "AND out.pos = $pos ORDER BY id LIMIT $limit;",
            pos=lexeme.fields.get("pos"),
            band=band,
            upper=band + 1,
        )
        fallback_senses = await query(
            "SELECT id, out FROM has_sense WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND in IN $lexemes ORDER BY id LIMIT $limit;",
            lexemes=[row["out"] for row in fallback[:LIMIT]],
        )
        for row in fallback_senses[:LIMIT]:
            tiers.setdefault(row["out"], 3)
        targets = {answer, *tiers, *excluded}
        # Each stage has a hard cap. Ambiguous/oversized ancestry fails closed,
        # rather than silently dropping synonym spellings from the safety set.
        paths = await query(
            "SELECT id, in, out FROM has_sense WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND out IN $targets ORDER BY id LIMIT $path_limit;",
            targets=list(targets),
            path_limit=LIMIT * 6 + 1,
        )
        if len(paths) > LIMIT * 6:
            return None
        ancestors = await query(
            "SELECT id, in, out FROM has_lexeme WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND out IN $lexemes ORDER BY id LIMIT $path_limit;",
            lexemes=list({row["in"] for row in paths}),
            path_limit=LIMIT * 6 + 1,
        )
        if len(ancestors) > LIMIT * 6:
            return None
        ids = targets | {row["in"] for row in paths} | {row["in"] for row in ancestors}
        records = await query(
            "SELECT * FROM $targets WHERE owner = NONE OR owner = $user;",
            targets=list(ids),
        )
        overlays = {RecordID("override", [user, target]): target for target in ids}
        changes = await query(
            "SELECT id, fields FROM $overlays WHERE owner = $user;",
            overlays=list(overlays),
        )
        effective = {row["id"]: row for row in records}
        for row in changes:
            target = overlays[row["id"]]
            if target in effective:
                allowed = TABLE_FIELDS[target.table_name]
                fields = {key: value for key, value in row["fields"].items() if key in allowed}
                effective[target] = _merge(effective[target], fields)
        found: dict[RecordID, list[DistractorRecord]] = {}
        selected: DistractorRecord | None = None
        for path in paths:
            sense_id, lexeme_id = path["out"], path["in"]
            for ancestor in ancestors:
                if ancestor["out"] != lexeme_id:
                    continue
                lemma_id = ancestor["in"]
                if not all(key in effective for key in (sense_id, lexeme_id, lemma_id)):
                    continue
                sense, lexeme, lemma = (
                    effective[sense_id],
                    effective[lexeme_id],
                    effective[lemma_id],
                )
                frequency = lemma.get("freq_zipf")
                record = DistractorRecord(
                    sense_id=encode_rid(sense_id, "sense"),
                    word=lemma.get("text", ""),
                    definition=sense.get("definition", ""),
                    pos=lexeme.get("pos"),
                    freq_zipf=frequency if isinstance(frequency, (int, float)) else None,
                    tier=tiers.get(sense_id, 0),
                )
                found.setdefault(sense_id, []).append(record)
                if sense_id == answer and lemma_id == answer_lemma and lexeme_id == answer_lexeme:
                    selected = record
        if selected is None:
            return None
        return DistractorPool(
            answer=selected,
            candidates=tuple(record for key in tiers for record in found.get(key, ())),
            synonyms=tuple(
                record for key in sorted(excluded, key=str) for record in found.get(key, ())
            ),
        )

    return await _atomic(db, operation)
