"""ORM models package.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogenerate and ``Base.metadata.create_all`` see the complete schema.
"""

# Redundant ``as`` aliases mark these names as explicit re-exports (PEP 484).
from app.db.base import Base as Base
from app.models.character import Character as Character
from app.models.enums import ParticipantRole as ParticipantRole
from app.models.enums import RoomStatus as RoomStatus
from app.models.initiative import InitiativeEntry as InitiativeEntry
from app.models.invite_link import InviteLink as InviteLink
from app.models.participant import Participant as Participant
from app.models.room import Room as Room
from app.models.token import Token as Token
