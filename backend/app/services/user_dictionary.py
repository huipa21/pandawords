from surrealdb import AsyncSurrealConnection, RecordID

from app.core.record_ids import decode_rid
from app.db import user_dictionary as repository
from app.domain.dictionary import DictionaryEntryRead, DictionaryRecordRead, DictionaryTable
from app.domain.user_dictionary import CustomSenseCreate
from app.services import dictionary


def target_id(table: DictionaryTable, value: str) -> RecordID:
    try:
        return decode_rid(value, table)
    except ValueError:
        raise repository.not_found() from None


async def read_entry(db: AsyncSurrealConnection, owner: str, lemma_id: str) -> DictionaryEntryRead:
    target_id("lemma", lemma_id)
    entry = await dictionary.read_entry(db, owner, lemma_id)
    if entry is None:
        raise repository.not_found()
    return entry


async def create_sense(
    db: AsyncSurrealConnection, owner: str, lexeme_id: str, data: CustomSenseCreate
) -> DictionaryRecordRead:
    return await repository.create_sense(db, owner, target_id("lexeme", lexeme_id), data)
