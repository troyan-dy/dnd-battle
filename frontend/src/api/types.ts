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

/** Read view of a character's stat block — drives the player's character panel. */
export interface CharacterResponse {
  id: string;
  room_id: string;
  name: string;
  max_hp: number;
  current_hp: number;
  /** http(s) portrait URL, or null. */
  portrait_url: string | null;
  ability_scores: AbilityScores;
  /** Active D&D 2024 condition names. */
  conditions: string[];
}

export interface ResolveInviteResponse {
  room_id: string;
  participant_id: string;
  role: ParticipantRole;
  /** null for a host (the DM controls no single character slot). */
  character_id: string | null;
}

/** Host request to place a token (bound to a character) on the board grid. */
export interface PlaceTokenRequest {
  character_id: string;
  /** Grid column (0-based); defaults to 0 server-side. */
  x?: number;
  /** Grid row (0-based); defaults to 0 server-side. */
  y?: number;
  /** Footprint in grid cells (1 = Medium, 2 = Large, ...); defaults to 1. */
  size?: number;
}

/** Host request to reposition/resize a token; omitted fields are unchanged. */
export interface UpdateTokenRequest {
  x?: number;
  y?: number;
  size?: number;
}

/** Board-state view of a single token: its binding and grid placement. */
export interface TokenResponse {
  id: string;
  room_id: string;
  character_id: string;
  x: number;
  y: number;
  size: number;
}

/** One combatant's seat in a room's initiative / turn order. */
export interface InitiativeEntryResponse {
  id: string;
  /** Bound character, or null for an NPC/monster combatant. */
  character_id: string | null;
  /** Display label shown in the tracker. */
  name: string;
  /** Rolled initiative value (higher acts first). */
  initiative: number;
  /** Resolved 0-based seat in the turn order. */
  order_index: number;
}

/**
 * The full turn-order snapshot: the ordered combatants + whose turn it is.
 * `active_index` is the 0-based seat whose turn it currently is (null when no
 * order is set = combat not started); `round` counts rounds.
 */
export interface InitiativeState {
  active_index: number | null;
  round: number;
  entries: InitiativeEntryResponse[];
}

/**
 * The FULL current board snapshot the server pushes to a client when it (re)joins
 * a room (Socket.IO `boardState` event). Mirrors `app.schemas.room.BoardState`.
 * A complete, idempotent read — reloading a link yields the same snapshot.
 */
export interface BoardState {
  room_id: string;
  tokens: TokenResponse[];
  characters: CharacterResponse[];
  initiative: InitiativeState;
}

// ---------------------------------------------------------------------------
// Versioned Action protocol — mirrors app/schemas/action.py (source of truth).
// An Action is a board change broadcast to everyone in a room. Clients send an
// ActionIntent; the server validates and broadcasts the resulting Action.
// ---------------------------------------------------------------------------

/** Current Action-protocol version (mirrors ACTION_PROTOCOL_VERSION). */
export const ACTION_PROTOCOL_VERSION = 1;

export type ActionType = 'move' | 'mark' | 'damage' | 'heal' | 'endTurn';

/** Move a token to a grid cell. */
export interface MovePayload {
  type: 'move';
  token_id: string;
  x: number;
  y: number;
}

/** A transient mark / ping placed on the board for everyone to see. */
export interface MarkPayload {
  type: 'mark';
  x: number;
  y: number;
  color?: string | null;
  label?: string | null;
}

/** Apply damage to a token (reduces HP, clamped at 0). */
export interface DamagePayload {
  type: 'damage';
  token_id: string;
  amount: number;
}

/** Heal a token (restores HP, clamped at the character's max HP). */
export interface HealPayload {
  type: 'heal';
  token_id: string;
  amount: number;
}

/** Advance the initiative order to the next combatant. */
export interface EndTurnPayload {
  type: 'endTurn';
}

/** Discriminated union of every concrete action payload (key: `type`). */
export type ActionPayload =
  MovePayload | MarkPayload | DamagePayload | HealPayload | EndTurnPayload;

/**
 * Client → server: a request to perform a board action. Carries only the
 * protocol version and payload; the server stamps actor/room/id itself.
 */
export interface ActionIntent {
  version?: number;
  payload: ActionPayload;
}

/**
 * Server → all clients: the validated, broadcast board action with
 * server-generated metadata. `seq` is a per-room monotonic counter.
 */
export interface Action {
  version: number;
  id: string;
  room_id: string;
  actor_participant_id: string;
  seq: number;
  payload: ActionPayload;
}
