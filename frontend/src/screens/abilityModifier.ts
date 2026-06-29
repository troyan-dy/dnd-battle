// Pure helper: D&D 2024 ability modifier from an ability score.
// Full rules math lands in the isolated rules engine (Phase 6); this is just the
// one formula the player's character panel needs to display modifiers.

/** floor((score - 10) / 2), formatted with an explicit sign (e.g. "+3", "-1"). */
export function abilityModifier(score: number): string {
  const mod = Math.floor((score - 10) / 2);
  return mod >= 0 ? '+' + String(mod) : String(mod);
}
