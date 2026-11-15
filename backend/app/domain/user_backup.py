"""User backup/restore models and the preference merge rule (pure, no I/O)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import AppError
from app.domain.auth import UserCreate, UserPreferences
from app.domain.bundle_import import ImportSummary
from app.domain.bundle_user import Preferences

USER_FORMAT = "pandawords.user"
_ACCOUNT_LANGS = ("source_lang", "target_lang")


class RestoreSummary(ImportSummary):
    """``already_restored``: this exact backup was restored before and nothing was changed."""

    already_restored: bool
    preferences_restored: list[str]
    preferences_kept: list[str]


class AlreadyRestored(AppError):
    """Raised inside the restore transaction to roll back a duplicate restore."""

    def __init__(self, summary: Mapping[str, Any]) -> None:
        super().__init__("backup.already_restored", 200, "Backup already restored.")
        self.summary = dict(summary)


@dataclass
class PreferenceMerge:
    prefs: dict[str, Any] = field(default_factory=dict[str, Any])
    langs: dict[str, str] = field(default_factory=dict[str, str])
    restored: list[str] = field(default_factory=list[str])
    kept: list[str] = field(default_factory=list[str])


def _default(key: str) -> Any:
    if key in _ACCOUNT_LANGS:
        return UserCreate.model_fields[key].default
    return UserPreferences.model_fields[key].default


def merge_preferences(account: Mapping[str, Any], bundled: Preferences) -> PreferenceMerge:
    """Restore a bundled preference only where the user still has the default (or no) value.

    A value the user has already changed is kept and reported, never silently overwritten.
    """
    current_prefs: dict[str, Any] = dict(account.get("prefs") or {})
    merge = PreferenceMerge(prefs=dict(current_prefs))
    for key, value in bundled.model_dump().items():
        current = account.get(key) if key in _ACCOUNT_LANGS else current_prefs.get(key)
        if current == value:
            continue
        if current is not None and current != _default(key):
            merge.kept.append(key)
            continue
        if key in _ACCOUNT_LANGS:
            merge.langs[key] = value
        else:
            merge.prefs[key] = value
        merge.restored.append(key)
    return merge
