// Renders the room's tokens inside the board's Konva stage.
//
// Each token is drawn in WORLD coordinates (aligned to the grid via `tokenRect`),
// so the parent stage transform (pan/zoom) applies automatically. A token shows
// its bound character's name, a live HP bar, and any current conditions — the
// display data the host/players need to read the encounter at a glance.
//
// Still PURELY LOCAL: this draws whatever the latest fetch returned; realtime
// updates land in Phase 4.

import { Group, Rect, Text } from 'react-konva';
import type { GridConfig } from './grid';
import { hpBarColor, hpFraction, tokenRect, type PlacedToken } from './tokens';

export interface TokenLayerProps {
  /** Tokens already joined to their character display data. */
  tokens: readonly PlacedToken[];
  /** Same grid the overlay uses, so tokens snap to cells. */
  config: GridConfig;
}

const BODY_FILL = 'rgba(56, 139, 253, 0.65)';
const BODY_STROKE = '#1f6feb';
const LABEL_FILL = '#ffffff';
const LABEL_BG = 'rgba(0, 0, 0, 0.55)';
const HP_TRACK = 'rgba(0, 0, 0, 0.55)';

export default function TokenLayer({ tokens, config }: TokenLayerProps) {
  return (
    <>
      {tokens.map(({ token, character }) => {
        const rect = tokenRect(token, config);
        const font = Math.max(8, config.cellSize * 0.22);
        const pad = font * 0.3;
        const barHeight = Math.max(3, config.cellSize * 0.1);
        const fraction = hpFraction(character.current_hp, character.max_hp);
        const conditions = character.conditions.length > 0 ? character.conditions.join(', ') : '';

        return (
          <Group key={token.id} listening={false}>
            {/* Footprint body */}
            <Rect
              x={rect.x}
              y={rect.y}
              width={rect.width}
              height={rect.height}
              fill={BODY_FILL}
              stroke={BODY_STROKE}
              strokeWidth={Math.max(1, config.cellSize * 0.03)}
              cornerRadius={Math.min(rect.width, rect.height) * 0.12}
              perfectDrawEnabled={false}
            />

            {/* Name label above the token */}
            <Rect
              x={rect.x}
              y={rect.y - font - pad * 2}
              width={rect.width}
              height={font + pad * 2}
              fill={LABEL_BG}
              cornerRadius={pad}
              perfectDrawEnabled={false}
            />
            <Text
              x={rect.x}
              y={rect.y - font - pad}
              width={rect.width}
              align="center"
              text={character.name}
              fontSize={font}
              fill={LABEL_FILL}
              listening={false}
              perfectDrawEnabled={false}
            />

            {/* HP bar pinned to the bottom of the footprint */}
            <Rect
              x={rect.x + pad}
              y={rect.y + rect.height - barHeight - pad}
              width={rect.width - pad * 2}
              height={barHeight}
              fill={HP_TRACK}
              cornerRadius={barHeight / 2}
              perfectDrawEnabled={false}
            />
            <Rect
              x={rect.x + pad}
              y={rect.y + rect.height - barHeight - pad}
              width={(rect.width - pad * 2) * fraction}
              height={barHeight}
              fill={hpBarColor(fraction)}
              cornerRadius={barHeight / 2}
              perfectDrawEnabled={false}
            />
            <Text
              x={rect.x}
              y={rect.y + rect.height - barHeight - pad * 2 - font}
              width={rect.width}
              align="center"
              text={`${character.current_hp}/${character.max_hp}`}
              fontSize={font * 0.8}
              fill={LABEL_FILL}
              listening={false}
              perfectDrawEnabled={false}
            />

            {/* Conditions below the token, if any */}
            {conditions && (
              <Text
                x={rect.x}
                y={rect.y + rect.height + pad}
                width={rect.width}
                align="center"
                text={conditions}
                fontSize={font * 0.8}
                fill="#f0d24b"
                listening={false}
                perfectDrawEnabled={false}
              />
            )}
          </Group>
        );
      })}
    </>
  );
}
