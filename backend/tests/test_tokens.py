"""Unit tests for invite-link token generation + hashing (pure functions)."""

from __future__ import annotations

import hashlib

from app.security.tokens import generate_token, hash_token


def test_generate_token_is_unguessable_and_unique() -> None:
    """Tokens are long, url-safe, and effectively never collide."""
    tokens = {generate_token() for _ in range(1000)}
    assert len(tokens) == 1000  # no collisions
    sample = next(iter(tokens))
    assert len(sample) >= 32
    assert sample.strip() == sample


def test_hash_token_is_sha256_hex_and_deterministic() -> None:
    """hash_token matches SHA-256 hex and is stable for the same input."""
    token = "example-plaintext-token"
    digest = hash_token(token)
    assert digest == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert len(digest) == 64
    assert hash_token(token) == digest  # deterministic


def test_hash_token_differs_from_plaintext() -> None:
    """The stored hash never equals the plaintext token."""
    token = generate_token()
    assert hash_token(token) != token
