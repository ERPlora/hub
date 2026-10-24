// «An approval is needed» (BASE-G136; the old hub's HUB_SHELL-F51): what is approved in the app's words, «Who approves
// it?» with the people who may do it themselves (live `base.approval.approvers`) on the till's faces and PIN pad
// (APP-BASE-3's `PinDoor`: with one person the pad is already theirs; «Another person» goes back), or their badge at any
// moment with nothing pressed first. An approval closes the dialog with its
// pass and says «Approved by <name>»; a refusal stays in the dialog, told from its code; «Cancel» closes it with none.
import { modalController } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import { toastSuccess } from '@erplora/ui/shell';
import ApprovalDialog from './ApprovalDialog.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const ionic = await importOriginal<typeof import('@ionic/vue')>();
  return { ...ionic, modalController: { ...ionic.modalController, dismiss: vi.fn(() => Promise.resolve(true)) } };
});

const QUESTION = { operation: 'sale.sale.void', label: 'Void a sale', fingerprint: 'f'.repeat(64) };
const ADAM = { id: '0199aaaa-0000-7000-8000-000000000002', name: 'Adam', initials: 'A' };
const OLGA = { id: '0199aaaa-0000-7000-8000-000000000001', name: 'Olga', initials: 'O' };
const PASS = { token: 'elev_pass', approver: 'Adam', expires_in: 120 };

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(ApprovalDialog, { props: { question: QUESTION }, ...options });
  const call = await m.live();
  return { ...m, call };
}

const byTestId = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;

function posted(m: { net: { api: { url: string; init: RequestInit }[] } }) {
  return m.net.api.map((call) => [new URL(call.url, 'http://a.localhost').pathname, JSON.parse(String(call.init.body))]);
}

async function typePin(pin: string) {
  for (const digit of pin) {
    (document.querySelector(`[data-testid="pinpad-key-${digit}"]`) as HTMLButtonElement).click();
    await flush();
  }
}

async function swipe(card: string) {
  for (const key of [...card, 'Enter']) document.dispatchEvent(new KeyboardEvent('keydown', { key }));
  await flush();
}

afterEach(() => {
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

describe('ApprovalDialog', () => {
  it('names what is approved in the app’s words and asks who approves it, by PIN or badge', async () => {
    const m = await open({ locale: 'es' });
    expect(m.client.stream.subscriptions('base.approval.approvers')[0]?.params).toEqual({ operation: 'sale.sale.void' });
    await m.result(m.call, 'base.approval.approvers', { people: [ADAM, OLGA], pin_length: 4 });
    const text = m.wrapper.text();
    expect(text).toContain('Hace falta una aprobación');
    expect(text).toContain('Se aprueba: Void a sale');
    expect(text).toContain('Pide a un encargado que introduzca su PIN para aprobarlo.');
    expect(text).toContain('…o que pase su placa: no hace falta pulsar nada antes.');
    expect(text).toContain('¿Quién lo aprueba?');
    expect(m.wrapper.findAll('[data-testid="pin-face"]').map((card) => card.attributes('title'))).toEqual(['Adam', 'Olga']);
  });

  it('an action the app does not name is still asked, in general words', async () => {
    const m = await mountBase(ApprovalDialog, { props: { question: { ...QUESTION, label: '' } } });
    expect(m.wrapper.text()).toContain('Approving: an action this app cannot name');
  });

  it('the person’s PIN approves it: the dialog closes with the pass and says who approved', async () => {
    const m = await open({ onApi: () => Response.json(PASS) });
    await m.result(m.call, 'base.approval.approvers', { people: [ADAM, OLGA], pin_length: 4 });
    await m.wrapper.get('[data-testid="pin-face"]').trigger('click');
    expect(document.querySelector('[aria-label="PIN of Adam"]')).not.toBeNull();
    await typePin('2581');
    expect(posted(m)).toEqual([
      ['/api/approvals', { operation: 'sale.sale.void', fingerprint: 'f'.repeat(64), person: ADAM.id, pin: '2581' }],
    ]);
    expect(modalController.dismiss).toHaveBeenCalledWith('elev_pass', 'approved');
    expect(toastSuccess).toHaveBeenCalledWith('Approved by Adam');
  });

  it('«Another person» goes back to the people', async () => {
    const m = await open();
    await m.result(m.call, 'base.approval.approvers', { people: [ADAM, OLGA], pin_length: 6 });
    await m.wrapper.get('[data-testid="pin-face"]').trigger('click');
    expect(m.wrapper.findAll('.pinpad__dot')).toHaveLength(6);
    (document.querySelector('[aria-label="Another person"]') as HTMLElement).click();
    await flush();
    expect(m.wrapper.findAll('[data-testid="pin-face"]')).toHaveLength(2);
  });

  it('a badge swiped at any moment approves it, with nothing pressed first', async () => {
    const m = await open({ onApi: () => Response.json(PASS) });
    await m.result(m.call, 'base.approval.approvers', { people: [ADAM], pin_length: 4 });
    await swipe('CARD0002');
    expect(posted(m)).toEqual([['/api/approvals', { operation: 'sale.sale.void', fingerprint: 'f'.repeat(64), badge: 'CARD0002' }]]);
    expect(modalController.dismiss).toHaveBeenCalledWith('elev_pass', 'approved');
  });

  it('a refusal stays in the dialog, told from its code', async () => {
    const cases: [string, number, string][] = [
      ['base.approval_refused', 401, 'Those details do not approve this. Check the name and the PIN, and try again.'],
      ['base.approver_cannot', 403, 'That person cannot approve this: ask somebody who may do it themselves.'],
      ['base.approval_not_needed', 409, 'This no longer needs an approval: do it again.'],
      ['base.approval_not_offered', 409, 'This is not approved with a PIN.'],
      ['base.too_many_attempts', 429, 'Too many wrong attempts. Wait 5 minutes (server words).'],
      ['internal_error', 500, 'Could not send the approval. Check the connection and try again.'],
    ];
    for (const [code, status, said] of cases) {
      const message = code === 'base.too_many_attempts' ? said : 'Server words';
      const m = await open({ onApi: () => Response.json({ error: { code, message } }, { status }) });
      await m.result(m.call, 'base.approval.approvers', { people: [ADAM], pin_length: 4 });
      await typePin('1111');
      expect(m.wrapper.text(), code).toContain(said);
      expect(modalController.dismiss, code).not.toHaveBeenCalled();
      m.wrapper.unmount();
      document.body.innerHTML = '';
    }
  });

  it('nobody with a PIN who may do it: says so, and the badge still works', async () => {
    const m = await open();
    await m.result(m.call, 'base.approval.approvers', { people: [], pin_length: 4 });
    expect(byTestId('approval-nobody')?.textContent).toContain(
      'Nobody here can approve this with a PIN. Somebody who may do it can swipe their badge.',
    );
  });

  it('people that cannot be read say so with «Retry», never «nobody»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.approval.approvers'), 'internal_error'));
    await flush();
    expect(m.wrapper.text()).toContain('Could not load who can approve it.');
    expect(byTestId('approval-nobody')).toBeNull();
    expect(m.wrapper.find('[data-testid="approval-retry"]').exists()).toBe(true);
  });

  it('«Cancel» closes it with no pass', async () => {
    const m = await open();
    await m.wrapper.get('[data-testid="approval-cancel"]').trigger('click');
    expect(modalController.dismiss).toHaveBeenCalledWith(null, 'cancel');
  });
});
