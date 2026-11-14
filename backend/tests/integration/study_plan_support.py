from datetime import UTC, datetime
from uuid import uuid4

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, relate
from app.db.srs import user_record
from app.domain.add_to_project import AddToProjectCreate
from app.domain.dictionary_keys import sense_key
from app.services import project_tree, srs
from app.services.add_to_project import add_to_project
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory
from tests.integration.srs_support import Study, create_study


async def three_senses(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    reader: LexiconReader,
) -> tuple[Study, list[str]]:
    study = await create_study(db, make_user, reader)
    flow = await add_to_project(
        db,
        reader,
        study.user.id,
        study.project.id,
        AddToProjectCreate(
            lemma_key=["en", "run"],
            selected_senses=[sense_key("en", "run", "verb", source_sense_id="run-flow")],
        ),
    )
    tree = await project_tree.read_tree(db, study.user.id, study.project.id, 1, 100, False)
    lexeme = decode_rid(tree.items[0].lexemes[0].lexeme.id, "lexeme")
    custom = RecordID("sense", uuid4().hex)
    user = user_record(study.user.id)
    await create(
        db,
        custom,
        {
            "owner": user,
            "definition": "My custom sense",
            "gloss": {"zh": "自定义"},
            "register": [],
            "domain": [],
            "examples": [],
            "rank": 99,
            "common": False,
            "source": "custom",
        },
    )
    await relate(db, "has_sense", lexeme, custom, {"owner": user, "rank": 99})
    await relate(
        db,
        "includes",
        decode_rid(study.project.id, "project"),
        custom,
        {
            "owner": user,
            "hidden": False,
            "added_at": datetime.now(UTC),
        },
    )
    await srs.reconcile_memberships(db, study.user.id)
    return study, [study.sense_id, flow.selected_sense_ids[0], encode_rid(custom, "sense")]
