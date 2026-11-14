import pytest
from fsrs import Rating
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid
from app.db.memory_schema_test_support import owned
from app.db.project_schema_test_support import set_hidden
from app.db.srs import user_record
from app.db.srs_test_support import remove_memory
from app.domain.projects import ProjectCreate
from app.services import projects, srs
from app.services.add_to_project import add_to_project
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory
from tests.integration.srs_support import create_study, graded

pytestmark = pytest.mark.integration


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def test_first_repeat_second_project_hidden_restore_and_users(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    user = user_record(study.user.id)
    initial = await srs.read_memory(db, study.user.id, study.sense_id)
    assert not initial.introduced and initial.card.last_review is None
    edges = await owned(db, "includes", user)
    for edge in edges:
        await set_hidden(db, edge["id"], user, True)
    assert await srs.reconcile_memberships(db, study.user.id) == 0
    await add_to_project(db, lexicon_reader, study.user.id, study.project.id, study.data)
    second = await projects.create_project(db, study.user.id, ProjectCreate(name="Second"))
    await add_to_project(db, lexicon_reader, study.user.id, second.id, study.data)
    assert await srs.read_memory(db, study.user.id, study.sense_id) == initial
    assert len(await owned(db, "memory", user)) == 1
    completed = await srs.apply_review(db, study.user.id, await graded(db, study), Rating.Good)
    for edge in await owned(db, "includes", user):
        await set_hidden(db, edge["id"], user, True)
    await add_to_project(db, lexicon_reader, study.user.id, study.project.id, study.data)
    assert await srs.read_memory(db, study.user.id, study.sense_id) == completed.memory
    other = await create_study(db, make_user, lexicon_reader)
    assert other.sense_id == study.sense_id
    assert (await srs.read_memory(db, other.user.id, other.sense_id)).id != initial.id
    await projects.delete_project(db, study.user.id, study.project.id)
    await projects.delete_project(db, study.user.id, second.id)
    assert await srs.read_memory(db, study.user.id, study.sense_id) == completed.memory


async def test_reconcile_preexisting_hidden_memberships_without_resetting(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    initial = await srs.read_memory(db, study.user.id, study.sense_id)
    await remove_memory(db, study.user.id, initial)
    user = user_record(study.user.id)
    before = await owned(db, "includes", user)
    for edge in before:
        await set_hidden(db, edge["id"], user, True)
    hidden = await owned(db, "includes", user)
    assert await srs.reconcile_memberships(db, study.user.id) == 1
    restored = await srs.read_memory(db, study.user.id, study.sense_id)
    assert not restored.introduced and restored.card.step == 0
    assert await srs.reconcile_memberships(db, study.user.id) == 0
    assert await srs.read_memory(db, study.user.id, study.sense_id) == restored
    assert await owned(db, "includes", user) == hidden
    assert decode_rid(restored.sense_id, "sense") == decode_rid(study.sense_id, "sense")


async def test_read_of_legacy_card_reconciles_hidden_selected_membership(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    memory = await srs.read_memory(db, study.user.id, study.sense_id)
    await remove_memory(db, study.user.id, memory)
    user = user_record(study.user.id)
    for edge in await owned(db, "includes", user):
        await set_hidden(db, edge["id"], user, True)
    new = await srs.read_memory(db, study.user.id, study.sense_id)
    assert not new.introduced
    assert await srs.reconcile_memberships(db, study.user.id) == 0
