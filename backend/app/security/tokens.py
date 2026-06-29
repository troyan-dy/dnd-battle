"""Invite-link token generation + hashing (architect-approved security design).

Mirrors the contract documented on :class:`app.models.invite_link.InviteLink`:

* **Unguessable.** Plaintext tokens come from :func:`secrets.token_urlsafe`, giving
  256 bits of entropy by default — infeasible to brute force or enumerate.
* **Never stored in the clear.** Only the SHA-256 hex digest is persisted, so a DB
  leak cannot reveal live links. The plaintext is returned to the caller exactly
  once (at creation) and never again.
* **Deterministic lookup.** Resolving an incoming link hashes the presented token
  and matches it against the unique ``token_hash`` column (see the resolve task).

This module is pure (no DB / transport imports) so it is trivially unit-testable
and reusable by every invite-link task in Phase 1.
"""

from __future__ import annotations

import hashlib
import secrets

# Entropy in bytes for a freshly minted token. 32 bytes -> 256 bits, encoded as
# ~43 url-safe chars. Comfortably beyond guessing range.
_TOKEN_NBYTES = 32


def generate_token() -> str:
    """Return a fresh, unguessable, URL-safe plaintext invite token.

    The returned value is a *secret*: show it to the host once, hash it for
    storage with :func:`hash_token`, and never persist the plaintext.
    """
    return secrets.token_urlsafe(_TOKEN_NBYTES)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest used as the stored ``token_hash``.

    Deterministic and stable, so the same plaintext always maps to the same
    digest for exact lookups. A fast hash is fine here because the input already
    carries full cryptographic entropy (unlike a low-entropy password).
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
