// What the WhatsApp e2e ask erplora.com's own test seed (`tests/e2e/panel/whatsapp_hub_seed.py` of its checkout, run by
// `seedErplora` of whatsapp-helpers.ts) and what it leaves in `a`, and the script that sets `a`'s plan there. No I/O
// here: whatsapp-helpers.ts runs the seed and the spec runs the script.

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

/** In erplora.com (`manage.py shell -c`): the WhatsApp messages a month of `a`'s plan become WA_LIMIT, and its photo
 *  is pushed to this Hub. It prints what the plan had before and whether the Hub took the photo. */
export const SET_PLAN = `
import json, os
from django.db import transaction
from django.utils import timezone
from hubs.models import Hub
from hubs.queries.plan_catalog import effective_plan
from hubs.services.hub_push import bump_state, sync_hub
hub = Hub.objects.get(slug="a")
plan = effective_plan(hub.id, timezone.now())
before = plan.whatsapp_messages_per_month
plan.whatsapp_messages_per_month = int(os.environ["WA_LIMIT"])
plan.save(update_fields=["whatsapp_messages_per_month"])
with transaction.atomic():
    bump_state(hub.id)
print(json.dumps({"before": before, "delivered": sync_hub(hub.id)}))
`;
