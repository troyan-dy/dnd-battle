// TypeScript mirrors of the backend Pydantic contracts (app/schemas/room.py).
// Keep these in sync with the server — Pydantic is the source of truth.

export type ParticipantRole = 'host' | 'player';
export type RoomStatus = 'lobby' | 'active' | 'ended';

export interface CreateRoomRequest {
  name: string;
  host_display_name?: string | null;
}

export interface RoomSummary {
  id: string;
  name: string;
  status: RoomStatus;
}

export interface InviteLink {
  /** Plaintext invite token — shown once, never stored. */
  token: string;
  /** Full shareable URL: {APP_BASE_URL}/join/{token}. */
  url: string;
}

export interface CreateRoomResponse {
  room: RoomSummary;
  host_participant_id: string;
  host_role: ParticipantRole;
  host_link: InviteLink;
}

/** The six D&D 2024 ability scores. Each is an integer 1–30 (10 = average). */
export interface AbilityScores {
  strength: number;
  dexterity: number;
  constitution: number;
  intelligence: number;
  wisdom: number;
  charisma: number;
}

/** Host request to add a player + their character slot to a room. */
export interface AddPlayerRequest {
  character_name: string;
  max_hp: number;
  ability_scores?: AbilityScores;
  /** Optional http(s) portrait image URL. */
  portrait_url?: string | null;
  display_name?: string | null;
}

/** Result of adding a player: their participant/character ids and invite link. */
export interface AddPlayerResponse {
  participant_id: string;
  character_id: string;
  role: ParticipantRole;
  invite_link: InviteLink;
}

export interface ResolveInviteResponse {
  room_id: string;
  participant_id: string;
  role: ParticipantRole;
  /** null for a host (the DM controls no single character slot). */
  character_id: string | null;
}
