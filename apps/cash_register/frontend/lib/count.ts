// The total of a count while it is typed (CASH_REGISTER-F06), the same the server adds up: each face value
// (major units, «0.05») scaled once with the currency's decimals and multiplied by whole pieces.

/** A box as whole pieces: blank, not a number or negative is none. */
export function pieces(raw: string | number | undefined): number {
  const n = Math.trunc(Number(raw ?? 0));
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** The total in minor units of the currency (`decimals`: 2 in EUR, 0 in JPY, 3 in KWD). */
export function countTotal(counts: Record<string, string | number>, decimals: number): number {
  let total = 0;
  for (const [face, raw] of Object.entries(counts)) total += Math.round(Number(face) * 10 ** decimals) * pieces(raw);
  return total;
}
