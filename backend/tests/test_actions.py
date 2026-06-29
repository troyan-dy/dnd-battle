"""Unit tests for the versioned Action protocol schema (app/schemas/action.py).

Pure-schema tests: they exercise the discriminated union, the per-action payload
bounds, and the protocol-version gate on both envelopes. No transport/DB.
"""

from __future__ import annotations

import uuid

import pytest
from app.schemas.action import (
    ACTION_PROTOCOL_VERSION,
    Action,
    ActionIntent,
    ActionType,
    AttackIntentPayload,
    AttackResultPayload,
    DamagePayload,
    EndTurnPayload,
    HealPayload,
    MarkPayload,
    MovePayload,
)
from app.schemas.room import GRID_COORD_MAX
from pydantic import ValidationError


def test_protocol_version_is_one() -> None:
    assert ACTION_PROTOCOL_VERSION == 1


def test_move_intent_parses_via_discriminator() -> None:
    token_id = uuid.uuid4()
    intent = ActionIntent.model_validate(
        {"payload": {"type": "move", "token_id": str(token_id), "x": 3, "y": 4}}
    )
    assert intent.version == ACTION_PROTOCOL_VERSION
    assert isinstance(intent.payload, MovePayload)
    assert intent.payload.type is ActionType.MOVE
    assert intent.payload.token_id == token_id
    assert (intent.payload.x, intent.payload.y) == (3, 4)


def test_mark_intent_optional_fields_default_none() -> None:
    intent = ActionIntent.model_validate({"payload": {"type": "mark", "x": 1, "y": 2}})
    assert isinstance(intent.payload, MarkPayload)
    assert intent.payload.color is None
    assert intent.payload.label is None


def test_damage_and_endturn_payloads_select_correct_member() -> None:
    dmg = ActionIntent.model_validate(
        {"payload": {"type": "damage", "token_id": str(uuid.uuid4()), "amount": 7}}
    )
    assert isinstance(dmg.payload, DamagePayload)
    assert dmg.payload.amount == 7

    end = ActionIntent.model_validate({"payload": {"type": "endTurn"}})
    assert isinstance(end.payload, EndTurnPayload)
    assert end.payload.type is ActionType.END_TURN


def test_heal_payload_selects_correct_member() -> None:
    token_id = uuid.uuid4()
    intent = ActionIntent.model_validate(
        {"payload": {"type": "heal", "token_id": str(token_id), "amount": 5}}
    )
    assert isinstance(intent.payload, HealPayload)
    assert intent.payload.type is ActionType.HEAL
    assert intent.payload.token_id == token_id
    assert intent.payload.amount == 5


@pytest.mark.parametrize("bad_amount", [0, -1, 1001])
def test_heal_amount_bounds_enforced(bad_amount: int) -> None:
    with pytest.raises(ValidationError):
        HealPayload(token_id=uuid.uuid4(), amount=bad_amount)


def test_attack_intent_parses_via_discriminator_with_defaults() -> None:
    attacker, target = uuid.uuid4(), uuid.uuid4()
    intent = ActionIntent.model_validate(
        {
            "payload": {
                "type": "attack",
                "attacker_token_id": str(attacker),
                "target_token_id": str(target),
            }
        }
    )
    assert isinstance(intent.payload, AttackIntentPayload)
    assert intent.payload.type is ActionType.ATTACK
    assert intent.payload.attacker_token_id == attacker
    assert intent.payload.target_token_id == target
    # Defaults: no bonus, a 1d6 strike.
    assert intent.payload.attack_bonus == 0
    assert intent.payload.damage == "1d6"


def test_attack_intent_rejects_malformed_damage_expression() -> None:
    with pytest.raises(ValidationError):
        AttackIntentPayload(
            attacker_token_id=uuid.uuid4(),
            target_token_id=uuid.uuid4(),
            damage="not-dice",
        )


@pytest.mark.parametrize("bad_bonus", [-21, 21])
def test_attack_bonus_bounds_enforced(bad_bonus: int) -> None:
    with pytest.raises(ValidationError):
        AttackIntentPayload(
            attacker_token_id=uuid.uuid4(),
            target_token_id=uuid.uuid4(),
            attack_bonus=bad_bonus,
        )


def test_attack_result_broadcasts_with_roll_breakdown() -> None:
    action = Action(
        id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        actor_participant_id=uuid.uuid4(),
        seq=3,
        payload=AttackResultPayload(
            attacker_token_id=uuid.uuid4(),
            target_token_id=uuid.uuid4(),
            attack_roll=14,
            attack_bonus=5,
            attack_total=19,
            damage="1d8+3",
            damage_rolls=[6],
            damage_total=9,
        ),
    )
    dumped = action.model_dump(mode="json")
    assert dumped["payload"]["type"] == "attack"
    assert dumped["payload"]["attack_total"] == 19
    assert dumped["payload"]["damage_total"] == 9
    reparsed = Action.model_validate(dumped)
    assert isinstance(reparsed.payload, AttackResultPayload)
    assert reparsed.payload.damage_rolls == [6]


def test_unknown_action_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionIntent.model_validate({"payload": {"type": "teleport", "x": 0, "y": 0}})


@pytest.mark.parametrize("bad_amount", [0, -1, 1001])
def test_damage_amount_bounds_enforced(bad_amount: int) -> None:
    with pytest.raises(ValidationError):
        DamagePayload(token_id=uuid.uuid4(), amount=bad_amount)


@pytest.mark.parametrize("bad_coord", [-1, GRID_COORD_MAX + 1])
def test_move_coords_bounded(bad_coord: int) -> None:
    with pytest.raises(ValidationError):
        MovePayload(token_id=uuid.uuid4(), x=bad_coord, y=0)


def test_mark_label_length_capped() -> None:
    with pytest.raises(ValidationError):
        MarkPayload(x=0, y=0, label="x" * 61)


def test_intent_rejects_unsupported_version() -> None:
    with pytest.raises(ValidationError):
        ActionIntent.model_validate({"version": 999, "payload": {"type": "endTurn"}})


def test_action_broadcast_roundtrips_with_server_metadata() -> None:
    action = Action(
        id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        actor_participant_id=uuid.uuid4(),
        seq=0,
        payload=MovePayload(token_id=uuid.uuid4(), x=5, y=6),
    )
    dumped = action.model_dump(mode="json")
    assert dumped["version"] == ACTION_PROTOCOL_VERSION
    assert dumped["payload"]["type"] == "move"
    reparsed = Action.model_validate(dumped)
    assert isinstance(reparsed.payload, MovePayload)
    assert reparsed.seq == 0


def test_action_rejects_unsupported_version() -> None:
    with pytest.raises(ValidationError):
        Action(
            version=2,
            id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            actor_participant_id=uuid.uuid4(),
            seq=0,
            payload=EndTurnPayload(),
        )


def test_action_seq_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        Action(
            id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            actor_participant_id=uuid.uuid4(),
            seq=-1,
            payload=EndTurnPayload(),
        )
