"""Versioned Action protocol — the realtime board event contract (CLAUDE.md).

An **Action** is a board change broadcast to everyone in a room: ``move``,
``mark``, ``damage``, ``endTurn`` … This module is the Pydantic *source of truth*
for those shapes (the TS client mirrors it).

Two envelopes encode CLAUDE.md architecture rule 1 ("server is authoritative;
clients send intents, the server validates and broadcasts the resulting Action"):

* :class:`ActionIntent` — **client → server**. Carries only the protocol
  ``version`` and the per-action ``payload``. It deliberately has *no* actor /
  room / id fields: those are stamped by the server from the authenticated
  connection so a client can never spoof who it is or what room it acts in.
* :class:`Action` — **server → all clients** in the room. The same ``payload``
  wrapped with server-generated metadata (``id``, ``room_id``,
  ``actor_participant_id``, monotonic ``seq``) for the broadcast.

Versioning: a single supported :data:`ACTION_PROTOCOL_VERSION`. The envelope's
``version`` field is validated, giving the server one clean place to refuse a
client whose protocol has drifted. Bump the constant and widen the check when an
incompatible change ships.

Per-action payloads form a **discriminated union** on their ``type`` field
(Pydantic ``Field(discriminator="type")``), so new action types are additive and
parse-time safe. The payloads themselves live in :mod:`app.schemas.payloads` and
:mod:`app.schemas.attack`. This module is pure schema: it holds no live BoardState
and does no validation-against-state or broadcasting — those are separate Phase 4
tasks.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.attack import AttackIntentPayload, AttackResultPayload
from app.schemas.payloads import (
    DamagePayload,
    EndTurnPayload,
    HealPayload,
    MarkPayload,
    MovePayload,
    SetVisibilityPayload,
)

# Current Action-protocol version. Clients stamp this on every intent; the server
# rejects anything it does not support. Bump on an incompatible change.
ACTION_PROTOCOL_VERSION = 1


# Discriminated unions of the concrete action payloads. Pydantic selects the member
# by the ``type`` field, so unknown / mismatched types fail to parse.
#
# Intent vs broadcast diverge ONLY for ``attack``: the client sends an
# :class:`AttackIntentPayload` (no roll), the server rolls and broadcasts an
# :class:`AttackResultPayload`. Every other action is identical in both directions.
IntentActionPayload = Annotated[
    MovePayload
    | MarkPayload
    | DamagePayload
    | HealPayload
    | AttackIntentPayload
    | SetVisibilityPayload
    | EndTurnPayload,
    Field(discriminator="type"),
]
BroadcastActionPayload = Annotated[
    MovePayload | MarkPayload | DamagePayload | HealPayload | AttackResultPayload | EndTurnPayload,
    Field(discriminator="type"),
]
# Backward-compatible alias: an INTENT payload (what ``validate_intent`` returns).
ActionPayload = IntentActionPayload


def _validate_protocol_version(version: int) -> int:
    """Reject any envelope whose protocol version the server does not support."""
    if version != ACTION_PROTOCOL_VERSION:
        raise ValueError(
            f"Unsupported action protocol version {version!r}; "
            f"server supports {ACTION_PROTOCOL_VERSION}."
        )
    return version


class ActionIntent(BaseModel):
    """Client → server: a request to perform a board action.

    Intentionally minimal — the server derives *who* is acting and *which room*
    from the authenticated connection, never from this payload.
    """

    version: int = Field(
        default=ACTION_PROTOCOL_VERSION, description="Action-protocol version the client speaks."
    )
    payload: IntentActionPayload

    @field_validator("version")
    @classmethod
    def _check_version(cls, version: int) -> int:
        return _validate_protocol_version(version)


class Action(BaseModel):
    """Server → all clients: the validated, broadcast board action.

    Wraps the same ``payload`` with server-stamped metadata. ``seq`` is a
    per-room monotonic counter clients can use to order / dedupe events.
    """

    version: int = Field(
        default=ACTION_PROTOCOL_VERSION, description="Action-protocol version of this broadcast."
    )
    id: uuid.UUID = Field(description="Server-generated unique id for this action.")
    room_id: uuid.UUID = Field(description="Room this action belongs to.")
    actor_participant_id: uuid.UUID = Field(
        description="Participant the server attributes this action to."
    )
    seq: int = Field(ge=0, description="Per-room monotonic sequence number.")
    payload: BroadcastActionPayload

    @field_validator("version")
    @classmethod
    def _check_version(cls, version: int) -> int:
        return _validate_protocol_version(version)
