from dataclasses import dataclass
from uuid import uuid4

from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.domain.add_to_project import AddToProjectCreate
from app.domain.auth import User
from app.domain.dictionary_keys import sense_key
from app.domain.projects import ProjectCreate, ProjectRead
from app.domain.srs import FrameworkGrade, GradedReview
from app.services import projects, srs
from app.services.add_to_project import add_to_project
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory


@dataclass
class Study:
    user: User
    project: ProjectRead
    sense_id: str
    data: AddToProjectCreate


async def create_study(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    reader: LexiconReader,
) -> Study:
    user = await make_user()
    project = await projects.create_project(db, user.id, ProjectCreate(name="Study"))
    data = AddToProjectCreate(
        lemma_key=["en", "run"],
        selected_senses=[sense_key("en", "run", "verb", source_sense_id="run-move")],
    )
    result = await add_to_project(db, reader, user.id, project.id, data)
    return Study(user, project, result.selected_sense_ids[0], data)


async def graded(
    db: AsyncSurrealConnection,
    study: Study,
    *,
    exercise: str = "cloze",
    kind: str = "recall",
    duration: int = 10000,
    correct: bool = True,
) -> GradedReview:
    memory = await srs.read_memory(db, study.user.id, study.sense_id)
    return await srs.grade_review(
        db,
        Settings(),
        study.user.id,
        attempt_id=uuid4().hex,
        project_id=study.project.id,
        sense_id=study.sense_id,
        expected_version=memory.version,
        grade=FrameworkGrade.model_validate(
            {
                "exercise": exercise,
                "kind": kind,
                "duration_ms": duration,
                "correct": correct,
            }
        ),
    )
