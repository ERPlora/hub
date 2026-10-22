// What erplora.com recorded of its pushes to this Hub, read back after Meta's webhook so that a message the Hub
// refused fails saying why (FIX-HUB-WHATSAPP-INBOX-MEDIA-E2E-NEEDS-SAAS-MEDIA-URL): an attachment erplora.com links on
// another origin than SAAS_URL's is refused (422) and the thread never fills, which said nothing before.
// flow: WHATSAPP_INBOX-F06
import { describe, expect, it } from 'vitest';

import { messageIds, type Push, pushProblem } from './whatsapp-pushes';

const WHERE = { saas: 'http://localhost:8241', database: 'saas_e2e_8241' };

/** A Meta notice of `a`'s number with one change `field` carrying `value`. */
const notice = (field: string, value: Record<string, unknown>) =>
  JSON.stringify({ object: 'whatsapp_business_account', entry: [{ id: '880000000000100', changes: [{ field, value }] }] });

const push = (over: Partial<Push>): Push => ({ waMessageId: 'e2e.wamid.1', attachment: false, delivered: true, error: '', ...over });

describe('messageIds', () => {
  it('takes the messages and the owner’s echoes a notice carries, never its statuses', () => {
    expect(messageIds(notice('messages', { messages: [{ id: 'e2e.wamid.1' }, { id: 'e2e.wamid.2' }] }))).toEqual(['e2e.wamid.1', 'e2e.wamid.2']);
    expect(messageIds(notice('smb_message_echoes', { message_echoes: [{ id: 'e2e.wamid.3' }] }))).toEqual(['e2e.wamid.3']);
    expect(messageIds(notice('messages', { statuses: [{ id: 'e2e.wamid.4', status: 'read' }] }))).toEqual([]);
  });
});

describe('pushProblem', () => {
  it('is empty when the Hub took every message', () => {
    const pushes = [push({ waMessageId: 'e2e.wamid.1', attachment: true }), push({ waMessageId: 'e2e.wamid.2' })];
    expect(pushProblem(['e2e.wamid.1', 'e2e.wamid.2'], pushes, WHERE)).toBe('');
  });

  it('names WHATSAPP_MEDIA_BASE_URL with SAAS_URL’s origin when the Hub refused an attachment', () => {
    const refused = push({ attachment: true, delivered: false, error: 'HTTP 422 internal.payload_invalid' });
    const problem = pushProblem(['e2e.wamid.1'], [refused], { ...WHERE, saas: 'http://localhost:8241/' });
    expect(problem).toContain('WHATSAPP_MEDIA_BASE_URL=http://localhost:8241 ');
    expect(problem).toContain('e2e.wamid.1');
    expect(problem).toContain('HTTP 422 internal.payload_invalid');
  });

  it('gives what erplora.com recorded, without the attachment’s variable, for any other message it could not hand over', () => {
    const textRefused = push({ delivered: false, error: 'HTTP 422 internal.payload_invalid' });
    const unreachable = push({ attachment: true, delivered: false, error: 'HTTP 503 hub_unavailable' });
    for (const one of [textRefused, unreachable]) {
      const problem = pushProblem(['e2e.wamid.1'], [one], WHERE);
      expect(problem).toContain('e2e.wamid.1');
      expect(problem).toContain(one.error);
      expect(problem).not.toContain('WHATSAPP_MEDIA_BASE_URL');
    }
  });

  it('names the database read when erplora.com kept no row of a message', () => {
    const problem = pushProblem(['e2e.wamid.1', 'e2e.wamid.2'], [push({ waMessageId: 'e2e.wamid.1' })], WHERE);
    expect(problem).toContain('e2e.wamid.2');
    expect(problem).toContain('saas_e2e_8241');
    expect(problem).not.toContain('e2e.wamid.1');
  });

  it('says every message it could not hand over, one per line', () => {
    const refused = (id: string) => push({ waMessageId: id, attachment: true, delivered: false, error: 'HTTP 422 internal.payload_invalid' });
    const problem = pushProblem(['e2e.wamid.1', 'e2e.wamid.2'], [refused('e2e.wamid.1'), refused('e2e.wamid.2')], WHERE);
    expect(problem.split('\n')).toHaveLength(2);
  });
});
