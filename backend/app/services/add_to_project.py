"""Materialize explicit selections and enqueue work in the membership transaction."""

from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.core.record_ids import decode_rid, encode_rid
from app.db import add_to_project as repository
from app.domain.add_to_project import (
    AddToProjectCreate,
    AddToProjectRead,
    AudioJobPayload,
    EnrichJobPayload,
)
from app.domain.jobs import JobCreate, JobRead
from app.services import dictionary, jobs, srs
from app.services.lexicon import LexiconReader


async def add_to_project(
    db: AsyncSurrealConnection,
    reader: LexiconReader,
    owner: str,
    project_id: str,
    data: AddToProjectCreate,
) -> AddToProjectRead:
    try:
        project = decode_rid(project_id, "project")
    except ValueError:
        raise AppError("project.not_found", 404, "Project not found.") from None

    async def operation(txn: UUID) -> AddToProjectRead:
        materialized = await dictionary.materialize_lemma(
            db,
            reader,
            str(data.lemma_key[1]),
            lang=str(data.lemma_key[0]),
            selected_senses=data.selected_senses,
            txn_id=txn,
        )
        memberships = await repository.include(
            db,
            owner,
            project,
            [
                decode_rid(materialized.lemma_id, "lemma"),
                *[decode_rid(sense, "sense") for sense in materialized.selected_sense_ids],
            ],
            txn_id=txn,
        )
        for sense in materialized.selected_sense_ids:
            await srs.ensure_card(db, owner, sense, txn_id=txn)
        queued: list[JobRead] = []

        async def enqueue(kind: str, payload: EnrichJobPayload | AudioJobPayload, key: str) -> None:
            job = await jobs.enqueue(
                db,
                JobCreate(type=kind, owner=owner, payload=payload.model_dump()),
                dedup_key=key,
                txn_id=txn,
            )
            queued.append(JobRead.model_validate(job.model_dump(exclude={"owner", "payload"})))

        for sense in materialized.selected_sense_ids:
            key = decode_rid(sense, "sense").id
            if not isinstance(key, list):
                raise ValueError("Expected a structured dictionary sense identity")
            lexeme = encode_rid(RecordID("lexeme", key[:4]), "lexeme")
            await enqueue(
                "enrich",
                EnrichJobPayload(
                    lemma_key=data.lemma_key,
                    lemma_id=materialized.lemma_id,
                    lexeme_id=lexeme,
                    sense_id=sense,
                ),
                f"dictionary:v1:sense:{sense}",
            )
        for lexeme in materialized.lexeme_ids:
            for accent in ("US", "UK"):
                await enqueue(
                    "audio",
                    AudioJobPayload(
                        lemma_key=data.lemma_key,
                        lemma_id=materialized.lemma_id,
                        lexeme_id=lexeme,
                        accent=accent,
                    ),
                    f"dictionary:v1:lexeme:{lexeme}:{accent}",
                )
        return AddToProjectRead(
            **materialized.model_dump(),
            project_id=project_id,
            membership_ids=memberships,
            jobs=queued,
        )

    return await repository.atomic_add(db, owner, project, operation)
