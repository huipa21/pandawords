"""Owner-filtered relation questions over existing semantic and derivation edges."""

from collections import defaultdict
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.record_ids import decode_rid, encode_rid
from app.db.auth import _atomic, _rows
from app.db.dictionary import _record
from app.db.srs import user_record
from app.domain.exercises import ExerciseContext
from app.domain.recognition import RelationQuestion, definition

LIMIT = 64


async def relation_questions(
    db: AsyncSurrealConnection, context: ExerciseContext
) -> tuple[RelationQuestion, ...]:
    async def operation(txn: UUID) -> tuple[RelationQuestion, ...]:
        user = user_record(context.owner)
        sense = decode_rid(context.sense_id, "sense")
        lexeme = decode_rid(context.lexeme.id, "lexeme")
        params = {"user": user, "sense": sense, "lexeme": lexeme, "limit": LIMIT + 1}
        semantic = await _rows(
            db,
            "SELECT id, in, out, type FROM relates_to "
            "WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND (in = $sense OR out = $sense) ORDER BY id LIMIT $limit;",
            params,
            txn_id=txn,
        )
        derivations = await _rows(
            db,
            "SELECT id, in, out, via FROM derives_to "
            "WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND (in = $lexeme OR out = $lexeme) ORDER BY id LIMIT $limit;",
            params,
            txn_id=txn,
        )
        if len(semantic) > LIMIT or len(derivations) > LIMIT:
            return ()

        async def contexts(target: RecordID) -> list[ExerciseContext] | None:
            # Resolve the target through accessible ancestry, applying only this owner's overlays.
            paths = await _rows(
                db,
                "SELECT id, in, out FROM has_sense "
                "WHERE (owner = NONE OR owner = $user) "
                "AND (in.owner = NONE OR in.owner = $user) "
                "AND (out.owner = NONE OR out.owner = $user) "
                "AND (in = $target OR out = $target) ORDER BY id LIMIT $limit;",
                {**params, "target": target},
                txn_id=txn,
            )
            if len(paths) > LIMIT:
                return None
            result: list[ExerciseContext] = []
            for path in paths:
                ancestors = await _rows(
                    db,
                    "SELECT id, in, out FROM has_lexeme "
                    "WHERE (owner = NONE OR owner = $user) "
                    "AND (in.owner = NONE OR in.owner = $user) "
                    "AND (out.owner = NONE OR out.owner = $user) "
                    "AND out = $target ORDER BY id LIMIT $limit;",
                    {**params, "target": path["in"]},
                    txn_id=txn,
                )
                if len(ancestors) > LIMIT:
                    return None
                for ancestor in ancestors:
                    lemma = await _record(db, user, ancestor["in"], txn)
                    selected_lexeme = await _record(db, user, path["in"], txn)
                    selected_sense = await _record(db, user, path["out"], txn)
                    if lemma is None or selected_lexeme is None or selected_sense is None:
                        continue
                    result.append(
                        context.model_copy(
                            update={
                                "sense_id": encode_rid(path["out"], "sense"),
                                "lemma": lemma,
                                "lexeme": selected_lexeme,
                                "sense": selected_sense,
                                "forms": (),
                            }
                        )
                    )
                    if len(result) > LIMIT:
                        return None
            return result

        groups: dict[tuple[str, str], list[ExerciseContext]] = defaultdict(list)
        for edge in [*semantic, *derivations]:
            derivation = edge["in"].table_name == "lexeme"
            selected = lexeme if derivation else sense
            outgoing = edge["in"] == selected
            target = edge["out"] if outgoing else edge["in"]
            if target == selected:
                continue
            kind = "derives_to" if derivation else str(edge["type"])
            direction = "from" if outgoing else "to"
            found = await contexts(target)
            if found is None:
                return ()
            groups[kind, direction].extend(found)
            if sum(map(len, groups.values())) > LIMIT:
                return ()
        word = str(context.lemma.fields.get("text", "")).strip()
        meaning = definition(context.sense.fields)
        if not word or not meaning:
            return ()
        questions: list[RelationQuestion] = []
        for (kind, direction), answers in sorted(groups.items()):
            words = (word, *(str(item.lemma.fields.get("text", "")) for item in answers))
            for answer in answers:
                if not definition(answer.sense.fields):
                    continue
                questions.append(
                    RelationQuestion(
                        text=f"Which word is linked {direction} “{word}” ({meaning}) by “{kind}”?",
                        answer=answer,
                        excluded_words=words,
                    )
                )
        return tuple(questions)

    return await _atomic(db, operation)
