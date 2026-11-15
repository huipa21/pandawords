"""Non-identifying bundle source fingerprints used to recognise a same-user restore.

``source = HMAC-SHA256(k, user_key || data.json sha256)`` with ``k`` derived from the server's
signing secret. It is bound to the exact ``data.json`` (so it cannot be copied onto other
content), differs for every distinct bundle, and reveals nothing about the account to anyone
without the secret. Rotating the secret only turns the progress default off.
"""

import hashlib
import hmac

from app.core.config import Settings
from app.domain.bundle_manifest import DATA_FILE, Manifest
from app.domain.identity import user_key

_CONTEXT = b"pandawords.bundle-source.v1\0"


def _key(settings: Settings) -> bytes:
    return hashlib.sha256(_CONTEXT + settings.jwt_secret.encode()).digest()


def fingerprint(settings: Settings, owner: str, data_sha256: str) -> str:
    message = f"{user_key(owner)}\0{data_sha256}".encode()
    return hmac.new(_key(settings), message, hashlib.sha256).hexdigest()


def same_source(settings: Settings, owner: str, manifest: Manifest) -> bool:
    """True only when this server issued the bundle to ``owner`` for exactly this data."""
    if manifest.source is None:
        return False
    data = next((entry for entry in manifest.entries if entry.path == DATA_FILE), None)
    if data is None:
        return False
    return hmac.compare_digest(fingerprint(settings, owner, data.sha256), manifest.source)
