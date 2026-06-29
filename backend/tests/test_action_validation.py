"""Tests for server-side Action intent validation (permissions + bounds).

Exercises ``app.services.actions.validate_intent`` against a seeded in-memory
database: host can target any token in its room, a player only its own token,
cross-owner / cross-room / unknown tokens are rejected, and non-token actions
(mark, endTurn) are allowed for any authenticated participant.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from app.models import (
    Base,
    Character,
    InitiativeEntry,
    Participant,
    ParticipantRole,
    Room,
    Token,
)
from app.schemas.action import (
    ActionIntent,
    AttackIntentPayload,
    DamagePayload,
    EndTurnPayload,
    HealPayload,
    MarkPayload,
    MovePayload,
    SetVisibilityPayload,
)
from app.services.actions import (
    IntentValidationError,
    apply_action,
    resolve_attack,
    validate_intent,
)
from app.services.board import build_board_state
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


class _ScriptedRandom(random.Random):
    """A Random whose ``randint`` returns a fixed script of values in order.

    Used to make server-authoritative dice deterministic: the script lists each
    d20 (one normally, two under advantage/disadvantage) followed by each damage die.
    """

    def __init__(self, values: list[int]) -> None:
        super().__init__()
        self._values = list(values)
        self._index = 0

    def randint(self, a: int, b: int) -> int:
        value = self._values[self._index]
        self._index += 1
        return value


@dataclass
class Seeded:
    factory: async_sessionmaker[AsyncSession]
    room_id: uuid.UUID
    # Player 1: owns char1 / token1
    p1_character_id: uuid.UUID
    token1_id: uuid.UUID
    # Player 2: owns char2 / token2
    p2_character_id: uuid.UUID
    token2_id: uuid.UUID
    # A token in a DIFFERENT room
    other_room_token_id: uuid.UUID


@pytest_asyncio.fixture
async def seeded() -> AsyncIterator[Seeded]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with factory() as session:
        room = Room(name="Goblin Ambush")
        other_room = Room(name="Other")
        session.add_all([room, other_room])
        await session.flush()

        char1 = Character(room_id=room.id, name="Aria", max_hp=24, current_hp=24)
        char2 = Character(room_id=room.id, name="Borin", max_hp=30, current_hp=30)
        other_char = Character(room_id=other_room.id, name="Stranger", max_hp=10, current_hp=10)
        session.add_all([char1, char2, other_char])
        await session.flush()

        session.add_all(
            [
                Participant(room_id=room.id, role=ParticipantRole.host, display_name="DM"),
                Participant(
                    room_id=room.id,
                    role=ParticipantRole.player,
                    character_id=char1.id,
                ),
                Participant(
                    room_id=room.id,
                    role=ParticipantRole.player,
                    character_id=char2.id,
                ),
            ]
        )
        token1 = Token(room_id=room.id, character_id=char1.id, x=1, y=1, size=1)
        token2 = Token(room_id=room.id, character_id=char2.id, x=2, y=2, size=1)
        other_token = Token(room_id=other_room.id, character_id=other_char.id, x=0, y=0, size=1)
        session.add_all([token1, token2, other_token])
        await session.commit()

        seeded = Seeded(
            factory=factory,
            room_id=room.id,
            p1_character_id=char1.id,
            token1_id=token1.id,
            p2_character_id=char2.id,
            token2_id=token2.id,
            other_room_token_id=other_token.id,
        )

    yield seeded
    await engine.dispose()


def _move(token_id: uuid.UUID, x: int = 5, y: int = 6) -> ActionIntent:
    return ActionIntent(payload=MovePayload(token_id=token_id, x=x, y=y))


def _damage(token_id: uuid.UUID, amount: int = 3) -> ActionIntent:
    return ActionIntent(payload=DamagePayload(token_id=token_id, amount=amount))


def _heal(token_id: uuid.UUID, amount: int = 3) -> ActionIntent:
    return ActionIntent(payload=HealPayload(token_id=token_id, amount=amount))


def _attack(
    attacker: uuid.UUID,
    target: uuid.UUID,
    *,
    damage: str = "1d6",
    damage_type: str = "slashing",
) -> ActionIntent:
    return ActionIntent(
        payload=AttackIntentPayload(
            attacker_token_id=attacker,
            target_token_id=target,
            damage=damage,
            damage_type=damage_type,  # type: ignore[arg-type]
        )
    )


# --- host permissions -----------------------------------------------------------


async def test_host_may_move_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=_move(seeded.token2_id),
        )
    assert isinstance(payload, MovePayload)
    assert payload.token_id == seeded.token2_id
    assert (payload.x, payload.y) == (5, 6)


async def test_host_may_damage_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=_damage(seeded.token1_id, amount=7),
        )
    assert isinstance(payload, DamagePayload)
    assert payload.amount == 7


async def test_host_may_heal_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=_heal(seeded.token2_id, amount=5),
        )
    assert isinstance(payload, HealPayload)
    assert payload.amount == 5


# --- player permissions ---------------------------------------------------------


async def test_player_may_move_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=_move(seeded.token1_id),
        )
    assert isinstance(payload, MovePayload)
    assert payload.token_id == seeded.token1_id


async def test_player_may_damage_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=_damage(seeded.token1_id),
        )
    assert isinstance(payload, DamagePayload)


async def test_player_may_heal_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=_heal(seeded.token1_id),
        )
    assert isinstance(payload, HealPayload)


async def test_player_may_not_heal_another_players_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=_heal(seeded.token2_id),
            )
    assert "your own token" in exc.value.reason


async def test_player_may_not_move_another_players_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=_move(seeded.token2_id),
            )
    assert "your own token" in exc.value.reason


async def test_player_may_not_damage_another_players_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError):
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p2_character_id,
                intent=_damage(seeded.token1_id),
            )


async def test_player_with_no_character_cannot_target_a_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError):
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=None,
                intent=_move(seeded.token1_id),
            )


# --- attack permissions + resolution --------------------------------------------


async def test_host_may_attack_any_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=_attack(seeded.token1_id, seeded.token2_id),
        )
    assert isinstance(payload, AttackIntentPayload)
    assert payload.attacker_token_id == seeded.token1_id
    assert payload.target_token_id == seeded.token2_id


async def test_player_may_attack_from_own_token(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=_attack(seeded.token1_id, seeded.token2_id),
        )
    assert isinstance(payload, AttackIntentPayload)


async def test_player_cannot_attack_from_a_foreign_token(seeded: Seeded) -> None:
    """The attacker token must be the player's own; attacking WITH token2 is rejected."""
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=_attack(seeded.token2_id, seeded.token1_id),
            )
    assert "your own token" in exc.value.reason


async def test_attack_target_must_be_on_this_board(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=_attack(seeded.token1_id, seeded.other_room_token_id),
            )
    assert "not on this board" in exc.value.reason


async def test_resolve_attack_hit_rolls_and_applies_damage(seeded: Seeded) -> None:
    """On a hit (total >= AC) the rolled damage is applied to the target (clamped)."""
    # char2 has the default AC 10; d20=15 + bonus 4 = 19 -> hit; damage dice 6,6.
    rng = _ScriptedRandom([15, 6, 6])
    async with seeded.factory() as session:
        result = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                attack_bonus=4,
                damage="2d6+1",
            ),
            rng=rng,
        )
        await session.commit()

    assert result.attack_roll == 15
    assert result.attack_total == 19
    assert result.armor_class == 10
    assert result.is_hit is True
    assert result.is_critical_hit is False
    assert result.advantage.value == "normal"
    assert result.damage_rolls == [6, 6]
    assert result.damage_total == 13  # 6 + 6 + 1 modifier, no defense
    assert result.defense.value == "normal"

    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        assert target.current_hp == 30 - 13


async def test_resolve_attack_miss_applies_no_damage(seeded: Seeded) -> None:
    """A miss (total < AC, not a natural 20) rolls no damage and leaves HP untouched."""
    # d20=2 + bonus 0 = 2 < AC 10 -> miss; no damage dice are rolled.
    rng = _ScriptedRandom([2])
    async with seeded.factory() as session:
        result = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                damage="2d6+1",
            ),
            rng=rng,
        )
        await session.commit()

    assert result.is_hit is False
    assert result.damage_rolls == []
    assert result.damage_total == 0

    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        assert target.current_hp == 30  # unchanged


async def test_resolve_attack_natural_20_always_hits(seeded: Seeded) -> None:
    """A natural 20 hits regardless of AC and is flagged a critical hit."""
    rng = _ScriptedRandom([20, 4])
    async with seeded.factory() as session:
        result = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                attack_bonus=-20,  # would miss on totals, but a nat 20 always hits
                damage="1d6",
            ),
            rng=rng,
        )
        await session.commit()

    assert result.is_hit is True
    assert result.is_critical_hit is True
    assert result.damage_total == 4


async def test_resolve_attack_applies_target_resistance(seeded: Seeded) -> None:
    """A target's resistance to the damage type halves the rolled damage (rounded down)."""
    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        target.resistances = {"fire": "resistance"}
        await session.commit()

    # hit (d20=18); damage 2d6 -> 5 + 6 = 11 raw, resisted -> 5.
    rng = _ScriptedRandom([18, 5, 6])
    async with seeded.factory() as session:
        result = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                damage="2d6",
                damage_type="fire",  # type: ignore[arg-type]
            ),
            rng=rng,
        )
        await session.commit()

    assert result.is_hit is True
    assert result.defense.value == "resistance"
    assert result.damage_type.value == "fire"
    assert result.damage_total == 5  # 11 // 2

    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        assert target.current_hp == 30 - 5


async def test_resolve_attack_advantage_from_target_condition(seeded: Seeded) -> None:
    """A restrained target grants attacks against it advantage (two d20s, higher used)."""
    async with seeded.factory() as session:
        target = await session.get(Character, seeded.p2_character_id)
        assert target is not None
        target.conditions = ["restrained"]
        await session.commit()

    # advantage rolls two d20s (3, 17) and uses the higher (17); then 1d6 -> 4.
    rng = _ScriptedRandom([3, 17, 4])
    async with seeded.factory() as session:
        result = await resolve_attack(
            session,
            room_id=seeded.room_id,
            payload=AttackIntentPayload(
                attacker_token_id=seeded.token1_id,
                target_token_id=seeded.token2_id,
                damage="1d6",
            ),
            rng=rng,
        )
        await session.commit()

    assert result.advantage.value == "advantage"
    assert result.attack_roll == 17  # the higher of the two d20s
    assert result.is_hit is True
    assert result.damage_total == 4


# --- state bounds ---------------------------------------------------------------


async def test_unknown_token_is_rejected(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=_move(uuid.uuid4()),
            )
    assert "not on this board" in exc.value.reason


async def test_token_from_another_room_is_rejected(seeded: Seeded) -> None:
    """Even the host of one room cannot act on a token belonging to a different room."""
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=_move(seeded.other_room_token_id),
            )
    assert "not on this board" in exc.value.reason


# --- non-token actions ----------------------------------------------------------


async def test_player_may_mark(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=ActionIntent(payload=MarkPayload(x=3, y=3, label="here")),
        )
    assert isinstance(payload, MarkPayload)
    assert payload.label == "here"


async def _seat_initiative(seeded: Seeded, *, order: list[uuid.UUID], active_index: int) -> None:
    """Seat the given characters in ``seeded``'s room and set the active turn."""
    async with seeded.factory() as session:
        room = await session.get(Room, seeded.room_id)
        assert room is not None
        for index, character_id in enumerate(order):
            session.add(
                InitiativeEntry(
                    room_id=seeded.room_id,
                    character_id=character_id,
                    name=f"C{index}",
                    initiative=20 - index,
                    order_index=index,
                )
            )
        room.initiative_active_index = active_index
        await session.commit()


async def test_host_may_always_end_turn(seeded: Seeded) -> None:
    """The host may advance the order even before combat has started."""
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=ActionIntent(payload=EndTurnPayload()),
        )
    assert isinstance(payload, EndTurnPayload)


async def test_player_cannot_end_turn_before_combat(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=ActionIntent(payload=EndTurnPayload()),
            )
    assert "Combat has not started" in exc.value.reason


async def test_player_may_end_their_own_turn(seeded: Seeded) -> None:
    await _seat_initiative(
        seeded, order=[seeded.p1_character_id, seeded.p2_character_id], active_index=0
    )
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.player,
            character_id=seeded.p1_character_id,
            intent=ActionIntent(payload=EndTurnPayload()),
        )
    assert isinstance(payload, EndTurnPayload)


async def test_player_cannot_end_another_combatants_turn(seeded: Seeded) -> None:
    await _seat_initiative(
        seeded, order=[seeded.p1_character_id, seeded.p2_character_id], active_index=0
    )
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p2_character_id,
                intent=ActionIntent(payload=EndTurnPayload()),
            )
    assert "not your turn" in exc.value.reason


# --- fog of war: hidden tokens (host-only) ---------------------------------------


def _set_visibility(token_id: uuid.UUID, hidden: bool) -> ActionIntent:
    return ActionIntent(payload=SetVisibilityPayload(token_id=token_id, hidden=hidden))


async def test_host_may_set_token_visibility(seeded: Seeded) -> None:
    """The host may hide/reveal any token in their room (fog of war)."""
    async with seeded.factory() as session:
        payload = await validate_intent(
            session,
            room_id=seeded.room_id,
            role=ParticipantRole.host,
            character_id=None,
            intent=_set_visibility(seeded.token2_id, hidden=True),
        )
    assert isinstance(payload, SetVisibilityPayload)
    assert payload.token_id == seeded.token2_id
    assert payload.hidden is True


async def test_player_cannot_set_token_visibility(seeded: Seeded) -> None:
    """A player may NOT hide/reveal tokens — even their own (CLAUDE.md rule 3)."""
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.player,
                character_id=seeded.p1_character_id,
                intent=_set_visibility(seeded.token1_id, hidden=True),
            )
    assert "host" in exc.value.reason.lower()


async def test_set_visibility_unknown_token_is_rejected(seeded: Seeded) -> None:
    async with seeded.factory() as session:
        with pytest.raises(IntentValidationError) as exc:
            await validate_intent(
                session,
                room_id=seeded.room_id,
                role=ParticipantRole.host,
                character_id=None,
                intent=_set_visibility(uuid.uuid4(), hidden=True),
            )
    assert "not on this board" in exc.value.reason


async def test_apply_set_visibility_flips_hidden_flag(seeded: Seeded) -> None:
    """apply_action toggles the durable Token.hidden flag both ways."""
    async with seeded.factory() as session:
        await apply_action(
            session,
            room_id=seeded.room_id,
            payload=SetVisibilityPayload(token_id=seeded.token2_id, hidden=True),
        )
        await session.commit()
    async with seeded.factory() as session:
        token = await session.get(Token, seeded.token2_id)
        assert token is not None
        assert token.hidden is True

    async with seeded.factory() as session:
        await apply_action(
            session,
            room_id=seeded.room_id,
            payload=SetVisibilityPayload(token_id=seeded.token2_id, hidden=False),
        )
        await session.commit()
    async with seeded.factory() as session:
        token = await session.get(Token, seeded.token2_id)
        assert token is not None
        assert token.hidden is False


async def test_build_board_state_filters_hidden_tokens_for_players(seeded: Seeded) -> None:
    """A player BoardState excludes hidden tokens AND their characters; host sees all."""
    async with seeded.factory() as session:
        token2 = await session.get(Token, seeded.token2_id)
        assert token2 is not None
        token2.hidden = True
        await session.commit()

    async with seeded.factory() as session:
        host_board = await build_board_state(session, seeded.room_id, include_hidden=True)
        player_board = await build_board_state(session, seeded.room_id, include_hidden=False)

    # Host receives every token (with the hidden flag) and every character.
    host_token_ids = {t.id for t in host_board.tokens}
    assert {seeded.token1_id, seeded.token2_id} <= host_token_ids
    assert any(t.id == seeded.token2_id and t.hidden for t in host_board.tokens)
    assert {seeded.p1_character_id, seeded.p2_character_id} <= {c.id for c in host_board.characters}

    # The player never receives the hidden token nor its character stat block.
    player_token_ids = {t.id for t in player_board.tokens}
    assert seeded.token1_id in player_token_ids
    assert seeded.token2_id not in player_token_ids
    player_character_ids = {c.id for c in player_board.characters}
    assert seeded.p1_character_id in player_character_ids
    assert seeded.p2_character_id not in player_character_ids
