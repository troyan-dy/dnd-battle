"""API tests for POST /rooms (create room -> room id + host link).

Runs against a fresh in-memory sqlite schema with get_session overridden, so no
Postgres is needed. Drives the real ASGI app via httpx.ASGITransport.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from app.db.session import get_session
from app.main import create_app
from app.models import (
    Base,
    Character,
    InviteLink,
    Participant,
    ParticipantRole,
    Room,
    RoomStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

ClientFactory = tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]]


@pytest_asyncio.fixture
async def client_and_factory() -> AsyncIterator[ClientFactory]:
    """Yield an ASGI client wired to a fresh in-memory DB plus its session factory."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_room_returns_id_and_host_link(
    client_and_factory: ClientFactory,
) -> None:
    """POST /rooms -> 201 with room id, host participant, and a host invite link."""
    client, factory = client_and_factory

    resp = await client.post(
        "/rooms",
        json={"name": "Goblin Ambush", "host_display_name": "DM Bob"},
    )

    assert resp.status_code == 201
    body = resp.json()

    # Room summary
    assert body["room"]["name"] == "Goblin Ambush"
    assert body["room"]["status"] == RoomStatus.lobby.value
    room_id = body["room"]["id"]

    # Host participant
    assert body["host_role"] == ParticipantRole.host.value
    host_id = body["host_participant_id"]

    # Host link: plaintext token + shareable url
    token = body["host_link"]["token"]
    assert token
    assert body["host_link"]["url"].endswith("/join/" + token)

    # Persistence: exactly one room, one host participant, one invite link.
    async with factory() as session:
        rooms = (await session.execute(select(Room))).scalars().all()
        assert len(rooms) == 1
        assert str(rooms[0].id) == room_id

        host = (await session.execute(select(Participant))).scalars().one()
        assert str(host.id) == host_id
        assert host.role is ParticipantRole.host
        assert host.character_id is None

        invite = (await session.execute(select(InviteLink))).scalars().one()
        assert str(invite.participant_id) == host_id
        assert str(invite.room_id) == room_id
        # Security invariant: only the SHA-256 hash is stored, never the plaintext.
        assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert invite.token_hash != token


@pytest.mark.asyncio
async def test_create_room_mints_unique_tokens(
    client_and_factory: ClientFactory,
) -> None:
    """Two rooms get distinct, unguessable host tokens (no reuse)."""
    client, _ = client_and_factory

    first = (await client.post("/rooms", json={"name": "A"})).json()
    second = (await client.post("/rooms", json={"name": "B"})).json()

    assert first["host_link"]["token"] != second["host_link"]["token"]
    assert len(first["host_link"]["token"]) >= 32


@pytest.mark.asyncio
async def test_create_room_rejects_blank_name(
    client_and_factory: ClientFactory,
) -> None:
    """An empty room name fails validation with 422."""
    client, _ = client_and_factory
    resp = await client.post("/rooms", json={"name": ""})
    assert resp.status_code == 422


async def _create_room(client: httpx.AsyncClient, name: str = "Room") -> str:
    """Helper: create a room and return its id."""
    resp = await client.post("/rooms", json={"name": name})
    assert resp.status_code == 201
    room_id: str = resp.json()["room"]["id"]
    return room_id


@pytest.mark.asyncio
async def test_add_player_mints_link_bound_to_character(
    client_and_factory: ClientFactory,
) -> None:
    """POST /rooms/{id}/participants -> 201: player + character slot + invite link."""
    client, factory = client_and_factory
    room_id = await _create_room(client, "Goblin Ambush")

    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={"character_name": "Aria", "max_hp": 24, "display_name": "Player One"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == ParticipantRole.player.value
    participant_id = body["participant_id"]
    character_id = body["character_id"]

    token = body["invite_link"]["token"]
    assert token
    assert body["invite_link"]["url"].endswith("/join/" + token)

    async with factory() as session:
        # Character slot created with current_hp seeded from max_hp.
        character = (await session.execute(select(Character))).scalars().one()
        assert str(character.id) == character_id
        assert character.name == "Aria"
        assert character.max_hp == 24
        assert character.current_hp == 24
        assert str(character.room_id) == room_id

        # Player participant bound to that character slot.
        player = (
            (
                await session.execute(
                    select(Participant).where(Participant.role == ParticipantRole.player)
                )
            )
            .scalars()
            .one()
        )
        assert str(player.id) == participant_id
        assert str(player.character_id) == character_id
        assert player.display_name == "Player One"

        # Per-participant invite link; only the SHA-256 hash is stored.
        invite = (
            (
                await session.execute(
                    select(InviteLink).where(InviteLink.participant_id == player.id)
                )
            )
            .scalars()
            .one()
        )
        assert str(invite.room_id) == room_id
        assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert invite.token_hash != token


@pytest.mark.asyncio
async def test_add_player_persists_ability_scores_and_portrait(
    client_and_factory: ClientFactory,
) -> None:
    """Ability scores + portrait URL from the config form are stored on the character."""
    client, factory = client_and_factory
    room_id = await _create_room(client)

    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={
            "character_name": "Aria",
            "max_hp": 24,
            "ability_scores": {
                "strength": 16,
                "dexterity": 14,
                "constitution": 13,
                "intelligence": 12,
                "wisdom": 10,
                "charisma": 8,
            },
            "portrait_url": "https://cdn.example.com/aria.png",
        },
    )
    assert resp.status_code == 201

    async with factory() as session:
        character = (await session.execute(select(Character))).scalars().one()
        assert character.ability_scores == {
            "strength": 16,
            "dexterity": 14,
            "constitution": 13,
            "intelligence": 12,
            "wisdom": 10,
            "charisma": 8,
        }
        assert character.portrait_url == "https://cdn.example.com/aria.png"


@pytest.mark.asyncio
async def test_add_player_defaults_ability_scores_to_ten(
    client_and_factory: ClientFactory,
) -> None:
    """Omitting ability scores / portrait keeps the legacy contract: all scores 10, no portrait."""
    client, factory = client_and_factory
    room_id = await _create_room(client)

    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={"character_name": "Aria", "max_hp": 10},
    )
    assert resp.status_code == 201

    async with factory() as session:
        character = (await session.execute(select(Character))).scalars().one()
        assert character.ability_scores == {
            "strength": 10,
            "dexterity": 10,
            "constitution": 10,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
        }
        assert character.portrait_url is None


@pytest.mark.asyncio
async def test_add_player_rejects_out_of_range_ability_score(
    client_and_factory: ClientFactory,
) -> None:
    """An ability score above 30 fails validation with 422."""
    client, _ = client_and_factory
    room_id = await _create_room(client)
    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={
            "character_name": "Aria",
            "max_hp": 10,
            "ability_scores": {"strength": 31},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_player_rejects_non_http_portrait_url(
    client_and_factory: ClientFactory,
) -> None:
    """A portrait_url without an http(s) scheme is rejected (422)."""
    client, _ = client_and_factory
    room_id = await _create_room(client)
    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={
            "character_name": "Aria",
            "max_hp": 10,
            "portrait_url": "javascript:alert(1)",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_player_blank_portrait_url_becomes_null(
    client_and_factory: ClientFactory,
) -> None:
    """A blank portrait_url is normalized to NULL rather than stored verbatim."""
    client, factory = client_and_factory
    room_id = await _create_room(client)
    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={"character_name": "Aria", "max_hp": 10, "portrait_url": "   "},
    )
    assert resp.status_code == 201

    async with factory() as session:
        character = (await session.execute(select(Character))).scalars().one()
        assert character.portrait_url is None


@pytest.mark.asyncio
async def test_add_player_mints_unique_tokens(
    client_and_factory: ClientFactory,
) -> None:
    """Two players in the same room get distinct tokens and distinct character slots."""
    client, _ = client_and_factory
    room_id = await _create_room(client)

    first = (
        await client.post(
            f"/rooms/{room_id}/participants",
            json={"character_name": "A", "max_hp": 10},
        )
    ).json()
    second = (
        await client.post(
            f"/rooms/{room_id}/participants",
            json={"character_name": "B", "max_hp": 10},
        )
    ).json()

    assert first["invite_link"]["token"] != second["invite_link"]["token"]
    assert first["character_id"] != second["character_id"]
    assert first["participant_id"] != second["participant_id"]


@pytest.mark.asyncio
async def test_add_player_unknown_room_returns_404(
    client_and_factory: ClientFactory,
) -> None:
    """Adding a player to a nonexistent room fails with 404 (no rows created)."""
    client, factory = client_and_factory
    missing_room = "00000000-0000-0000-0000-000000000000"

    resp = await client.post(
        f"/rooms/{missing_room}/participants",
        json={"character_name": "Ghost", "max_hp": 5},
    )
    assert resp.status_code == 404

    async with factory() as session:
        assert (await session.execute(select(Character))).scalars().all() == []
        assert (await session.execute(select(InviteLink))).scalars().all() == []


@pytest.mark.asyncio
async def test_add_player_rejects_nonpositive_hp(
    client_and_factory: ClientFactory,
) -> None:
    """max_hp must be > 0 (422)."""
    client, _ = client_and_factory
    room_id = await _create_room(client)
    resp = await client.post(
        f"/rooms/{room_id}/participants",
        json={"character_name": "Aria", "max_hp": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_revoke_disables_link_and_breaks_resolve(
    client_and_factory: ClientFactory,
) -> None:
    """Revoking a participant's link sets revoked_at and makes resolve 404."""
    client, factory = client_and_factory
    room_id = await _create_room(client)
    player = (
        await client.post(
            f"/rooms/{room_id}/participants",
            json={"character_name": "Aria", "max_hp": 10},
        )
    ).json()
    participant_id = player["participant_id"]
    token = player["invite_link"]["token"]

    # Link resolves before revocation.
    assert (await client.get(f"/invites/{token}")).status_code == 200

    resp = await client.post(f"/rooms/{room_id}/participants/{participant_id}/revoke")
    assert resp.status_code == 200
    assert resp.json()["revoked"] == 1

    # The token no longer resolves (uniform 404, no enumeration oracle).
    after = await client.get(f"/invites/{token}")
    assert after.status_code == 404
    assert after.json()["detail"] == "Invalid or expired invite link."

    # revoked_at is persisted on the link row.
    async with factory() as session:
        invite = (
            (
                await session.execute(
                    select(InviteLink).where(InviteLink.participant_id == uuid.UUID(participant_id))
                )
            )
            .scalars()
            .one()
        )
        assert invite.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_is_idempotent(
    client_and_factory: ClientFactory,
) -> None:
    """A second revoke call disables 0 more links (idempotent)."""
    client, _ = client_and_factory
    room_id = await _create_room(client)
    player = (
        await client.post(
            f"/rooms/{room_id}/participants",
            json={"character_name": "Aria", "max_hp": 10},
        )
    ).json()
    participant_id = player["participant_id"]

    first = await client.post(f"/rooms/{room_id}/participants/{participant_id}/revoke")
    assert first.status_code == 200
    assert first.json()["revoked"] == 1

    second = await client.post(f"/rooms/{room_id}/participants/{participant_id}/revoke")
    assert second.status_code == 200
    assert second.json()["revoked"] == 0


@pytest.mark.asyncio
async def test_revoke_unknown_participant_returns_404(
    client_and_factory: ClientFactory,
) -> None:
    """Revoking links for a nonexistent participant fails with 404."""
    client, _ = client_and_factory
    room_id = await _create_room(client)
    missing = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(f"/rooms/{room_id}/participants/{missing}/revoke")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_participant_in_other_room_returns_404(
    client_and_factory: ClientFactory,
) -> None:
    """A participant cannot be revoked via a different room's id (cross-room guard)."""
    client, _ = client_and_factory
    room_a = await _create_room(client, "A")
    room_b = await _create_room(client, "B")
    player = (
        await client.post(
            f"/rooms/{room_a}/participants",
            json={"character_name": "Aria", "max_hp": 10},
        )
    ).json()
    participant_id = player["participant_id"]
    token = player["invite_link"]["token"]

    # Wrong room id -> 404 and the link stays active.
    resp = await client.post(f"/rooms/{room_b}/participants/{participant_id}/revoke")
    assert resp.status_code == 404
    assert (await client.get(f"/invites/{token}")).status_code == 200


@pytest.mark.asyncio
async def test_get_character_returns_stat_block(
    client_and_factory: ClientFactory,
) -> None:
    """GET /rooms/{id}/characters/{cid} -> 200: the player view's character panel data."""
    client, _ = client_and_factory
    room_id = await _create_room(client, "Crypt")
    player = (
        await client.post(
            f"/rooms/{room_id}/participants",
            json={
                "character_name": "Aria",
                "max_hp": 24,
                "ability_scores": {
                    "strength": 8,
                    "dexterity": 16,
                    "constitution": 14,
                    "intelligence": 12,
                    "wisdom": 10,
                    "charisma": 18,
                },
                "portrait_url": "https://example.com/aria.png",
            },
        )
    ).json()
    character_id = player["character_id"]

    resp = await client.get(f"/rooms/{room_id}/characters/{character_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == character_id
    assert body["room_id"] == room_id
    assert body["name"] == "Aria"
    assert body["max_hp"] == 24
    assert body["current_hp"] == 24
    assert body["portrait_url"] == "https://example.com/aria.png"
    assert body["ability_scores"]["dexterity"] == 16
    assert body["ability_scores"]["charisma"] == 18
    assert body["conditions"] == []


@pytest.mark.asyncio
async def test_get_character_defaults_scores_when_omitted(
    client_and_factory: ClientFactory,
) -> None:
    """A character added without scores reads back all-10 defaults and no portrait."""
    client, _ = client_and_factory
    room_id = await _create_room(client)
    player = (
        await client.post(
            f"/rooms/{room_id}/participants",
            json={"character_name": "Bram", "max_hp": 11},
        )
    ).json()
    character_id = player["character_id"]

    body = (await client.get(f"/rooms/{room_id}/characters/{character_id}")).json()

    assert body["portrait_url"] is None
    assert body["ability_scores"] == {
        "strength": 10,
        "dexterity": 10,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
    }


@pytest.mark.asyncio
async def test_get_character_unknown_returns_404(
    client_and_factory: ClientFactory,
) -> None:
    """An unknown character id -> 404."""
    client, _ = client_and_factory
    room_id = await _create_room(client)
    missing = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/rooms/{room_id}/characters/{missing}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_character_in_other_room_returns_404(
    client_and_factory: ClientFactory,
) -> None:
    """A character cannot be read via a different room's id (cross-room guard)."""
    client, _ = client_and_factory
    room_a = await _create_room(client, "A")
    room_b = await _create_room(client, "B")
    player = (
        await client.post(
            f"/rooms/{room_a}/participants",
            json={"character_name": "Aria", "max_hp": 10},
        )
    ).json()
    character_id = player["character_id"]

    resp = await client.get(f"/rooms/{room_b}/characters/{character_id}")
    assert resp.status_code == 404
