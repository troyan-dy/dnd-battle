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

export interface ResolveInviteResponse {
  room_id: string;
  participant_id: string;
  role: ParticipantRole;
  /** null for a host (the DM controls no single character slot). */
  character_id: string | null;
}
