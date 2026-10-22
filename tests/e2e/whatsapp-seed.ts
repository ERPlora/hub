// What the WhatsApp e2e ask erplora.com's own test seed (`tests/e2e/panel/whatsapp_hub_seed.py` of its checkout, run by
// `seedErplora` of whatsapp-helpers.ts) and what it leaves in `a`. No I/O here: whatsapp-helpers.ts runs the seed.

/** What the seed leaves besides the number: `used`, the WhatsApp messages `a` sent this month in erplora.com (0 when
 *  not given: no send of the e2e is stopped; the plan's allowance makes the send that reaches it refused). */
export interface ErploraSeed {
  used?: number;
}

/** The seed's arguments after the hubs' ids for `seed`; it throws on what the seed's `--used` would refuse. */
export function seedArguments(seed: ErploraSeed): string[] {
  if (seed.used === undefined) return [];
  if (!Number.isSafeInteger(seed.used) || seed.used < 0) {
    throw new Error(`seedErplora: used is a whole number not below zero, not ${seed.used}.`);
  }
  return ['--used', String(seed.used)];
}

/** `a`'s templates as the seed keeps them after reading Meta's list (its `TEMPLATES`): one approved, one in review, one
 *  rejected with Meta's reason (INVALID_FORMAT) and one made in WhatsApp Manager with a photo header and a named
 *  variable, which the Hub cannot fill. Their `e2e_` names are deleted by cleanUp after a run. */
export const SEED_TEMPLATES = {
  approved: 'e2e_seed_recordatorio_cita',
  inReview: 'e2e_seed_oferta_color',
  rejected: 'e2e_seed_cambio_horario',
  manager: 'e2e_seed_bienvenida_foto',
} as const;
