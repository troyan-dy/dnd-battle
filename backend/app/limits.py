"""Shared length limits for persisted text columns and their API contracts.

The ORM columns (``app.models``) and the Pydantic request schemas
(``app.schemas``) must agree on these bounds, so they live in one place instead
of being repeated as bare numbers in both layers.
"""

from typing import Final

# Room / character / participant / initiative-combatant display names.
NAME_MAX_LENGTH: Final = 120

# An http(s) URL stored for a character portrait.
URL_MAX_LENGTH: Final = 2048

# A server-generated map image filename (``MAP_STORAGE_DIR``-relative).
MAP_PATH_MAX_LENGTH: Final = 255

# A validated, allowlisted image MIME type.
CONTENT_TYPE_MAX_LENGTH: Final = 100

# A SHA-256 hex digest (the stored invite ``token_hash``).
TOKEN_HASH_LENGTH: Final = 64
