// What erplora.com recorded of its pushes to this Hub (door 1), told in words. erplora.com pushes each message Meta
// posts to its webhook within that same request and keeps the Hub's answer on the message's delivery (`delivered_at`,
// or `last_error` as `HTTP <status> <code>`), so once its webhook answered, its database says whether this Hub took
// the message. The one refusal a stack causes by itself: erplora.com links an attachment on its
// `WHATSAPP_MEDIA_BASE_URL` (`http://localhost:8001` when unset, with DEBUG) and this Hub takes only its SAAS_URL's
// origin (`_from_erplora` in apps/whatsapp_inbox/schemas.py), so a run whose erplora.com is elsewhere gets a 422 and
// a thread that never fills (FIX-HUB-WHATSAPP-INBOX-MEDIA-E2E-NEEDS-SAAS-MEDIA-URL). No Playwright and no I/O here:
// whatsapp-helpers.ts reads the rows.

/** One message erplora.com took from Meta's webhook and pushed to this Hub (door 1), as its database recorded it. */
export interface Push {
  waMessageId: string;
  attachment: boolean;
  delivered: boolean;
  error: string;
}

/** Where the run's erplora.com is: its origin (`SAAS_URL`) and the database its rows are read from. */
export interface ErploraOfRun {
  saas: string;
  database: string;
}

interface Notice {
  entry?: { changes?: { value?: { messages?: { id: string }[]; message_echoes?: { id: string }[] } }[] }[];
}

/** The WhatsApp ids of the customers' messages and of the owner's echoes a Meta notice carries (statuses are not
 *  messages: erplora.com pushes them through door 2). */
export function messageIds(notice: string): string[] {
  const { entry = [] } = JSON.parse(notice) as Notice;
  return entry.flatMap(({ changes = [] }) =>
    changes.flatMap(({ value = {} }) => [...(value.messages ?? []), ...(value.message_echoes ?? [])].map(({ id }) => id)),
  );
}

/** Why erplora.com did not hand each of `ids` over to this Hub, one line each; `''` when this Hub took them all. */
export function pushProblem(ids: string[], pushes: Push[], where: ErploraOfRun): string {
  const byId = new Map(pushes.map((push) => [push.waMessageId, push]));
  return ids
    .map((id) => {
      const push = byId.get(id);
      if (!push) return `erplora.com's database ${where.database} keeps no message ${id}: is SAAS_URL's erplora.com running on it (E2E_SAAS_DB)?`;
      if (push.delivered) return '';
      const recorded = push.error || 'nothing recorded: see its log';
      if (push.attachment && push.error.startsWith('HTTP 422 ')) {
        const origin = new URL(where.saas).origin;
        return (
          `This Hub refused the attachment of ${id} from erplora.com (${recorded}): erplora.com links attachments on its ` +
          `WHATSAPP_MEDIA_BASE_URL (http://localhost:8001 when unset) and this Hub takes only its SAAS_URL's origin. ` +
          `Start erplora.com with WHATSAPP_MEDIA_BASE_URL=${origin} (whatsapp-helpers.ts).`
        );
      }
      return `This Hub did not take ${id} from erplora.com (${recorded}).`;
    })
    .filter(Boolean)
    .join('\n');
}
