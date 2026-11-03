// A record (VERIFACTU-F17, F18, F24, F25, F30, F35): «Record <number>» with its status and environment, why it is not in
// the AEAT yet (or that the AEAT rejected it and what to do), its invoice, its chain, its QR, the AEAT's answer and
// its XML; «Send now», «Ask the AEAT», «Correct» and «Cancel record» where they apply and for whoever may.
import { toast, toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, errorFrame, flush, type MountOptions, mountVerifactu } from '../__tests__/mount-verifactu';
import type { RecordOut } from '../operations';
import RecordDetailPage from './RecordDetailPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toast: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => {
  mocks.confirm.mockReset();
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toast).mockClear();
});

const OP = 'verifactu.record.get';

const RECORD: RecordOut = {
  id: 'r1',
  sequence: 2,
  record_type: 'alta',
  invoice_id: 'i1',
  invoice_number: 'TICKET-2026-000002',
  issue_date: '2026-10-14',
  invoice_type: 'F2',
  issuer_name: 'Peluquería Ana SL',
  issuer_nif: 'B12345674',
  total_amount: 1210,
  environment: 'testing',
  status: 'pending',
  correction: false,
  qr_url: 'https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674&numserie=TICKET-2026-000002',
  created_at: '2026-10-14T10:00:00Z',
  operation_date: null,
  rectification_kind: '',
  rectified: [],
  substituted: [],
  description: 'Venta 20261014-0002',
  recipient_name: '',
  recipient_tax_id: '',
  recipient_country: '',
  base_amount: 1000,
  tax_amount: 210,
  previous_rejection: '',
  corrects_id: null,
  cancels_id: null,
  previous_fingerprint: 'B'.repeat(64),
  previous_number: 'TICKET-2026-000001',
  generated_at: '2026-10-14T12:00:00+02:00',
  fingerprint: 'A'.repeat(64),
  qr_svg: 'data:image/svg+xml;base64,PHN2Zy8+',
  envelope: '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope/>',
  attempts: 0,
  next_attempt_at: '2026-10-14T10:00:00Z',
  transmitted_at: null,
  transmission_id: null,
  envelope_digest: '',
  incident: false,
  csv: '',
  aeat_code: '',
  aeat_message: '',
  waiting: [{ code: 'gateway_unavailable', message: "ERPlora's sending gateway is not configured on this server" }],
  can_transmit: true,
  can_correct: false,
  can_cancel: true,
  events: [
    {
      id: 'e1',
      created_at: '2026-10-14T10:00:00Z',
      kind: 'record_created',
      severity: 'info',
      message: 'Registration record #2 sealed for invoice TICKET-2026-000002.',
      record_id: 'r1',
      invoice_number: 'TICKET-2026-000002',
    },
  ],
};

async function setup(record: Partial<RecordOut> = {}, options: MountOptions = {}) {
  const m = await mountVerifactu(RecordDetailPage, { props: { id: 'r1' }, path: '/verifactu/records/r1', ...options });
  await m.live();
  await m.result(OP, { ...RECORD, ...record });
  return m;
}

describe('RecordDetailPage', () => {
  it('follows its record by id and names it by its invoice', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ record_id: 'r1' }]);
    expect(s.find('verifactu-record-title').text()).toBe('Record TICKET-2026-000002');
    expect(s.find('verifactu-record-status').text()).toContain('Pending');
  });

  it('says why it is not in the AEAT yet and that it goes out by itself once that is resolved', async () => {
    const s = await setup();
    const notice = s.find('verifactu-record-waiting');
    expect(notice.text()).toContain('Not at the AEAT yet');
    expect(notice.text()).toContain("ERPlora's sending gateway is not configured on this server");
    expect(notice.text()).toContain('as soon as that is resolved');
  });

  it('when every wait clears by itself it goes out with the next pass and there is nothing to do', async () => {
    const s = await setup({
      waiting: [
        { code: 'aeat_wait', message: 'the AEAT asked to wait until 10:01:00' },
        { code: 'unreachable', message: 'the gateway or the AEAT could not be reached (timeout)' },
      ],
    });
    const notice = s.find('verifactu-record-waiting');
    expect(notice.text()).toContain('It goes out by itself with the next pass');
    expect(notice.text()).toContain('You do not have to do anything');
    expect(notice.text()).not.toContain('as soon as that is resolved');
  });

  // hub#454, VERIFACTU-F17: one «when». A wait that something has to resolve (a refusal of the gateway that is not
  // sent again by itself, the authorisation, a business ERPlora has not linked) never says «nothing to do».
  it.each(['refused', 'representation_not_approved', 'hub_unregistered', 'gateway_unavailable'])(
    'with a %s wait it goes out once resolved, never «nothing to do»',
    async (code) => {
      const s = await setup({
        waiting: [
          { code: 'aeat_wait', message: 'the AEAT asked to wait until 10:01:00' },
          { code, message: `why: ${code}` },
        ],
      });
      const notice = s.find('verifactu-record-waiting');
      expect(notice.text()).toContain(`why: ${code}`);
      expect(notice.text()).toContain('It goes out by itself, in order and declared as late, as soon as that is resolved.');
      expect(notice.text()).not.toContain('You do not have to do anything');
      expect(notice.text()).not.toContain('with the next pass');
    },
  );

  it('outside Spain it says why and never that it goes out by itself', async () => {
    // FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN: VeriFactu is only for Spain, the record is never sent.
    const why = 'this business is not in Spain: VeriFactu is only for businesses in Spain, so nothing is sent to the AEAT';
    const s = await setup({ waiting: [{ code: 'outside_spain', message: why }], next_attempt_at: null, can_transmit: false });
    const notice = s.find('verifactu-record-waiting');
    expect(notice.text()).toContain(why);
    expect(notice.text()).not.toContain('It goes out by itself');
    expect(notice.text()).not.toContain('Next attempt');
  });

  it('a rejected record says the AEAT’s code and what to do', async () => {
    const s = await setup({ status: 'rejected', waiting: [], aeat_code: '1189', aeat_message: 'Falta Destinatarios', can_transmit: false, can_correct: true, can_cancel: false });
    expect(s.find('verifactu-record-waiting').exists()).toBe(false);
    const notice = s.find('verifactu-record-rejected');
    expect(notice.text()).toContain('The AEAT rejected it');
    expect(notice.text()).toContain('1189');
    expect(notice.text()).toContain('rectify it in Invoicing');
  });

  it('shows its chain, its QR and its XML', async () => {
    const s = await setup();
    expect(s.find('verifactu-record-fingerprint').text()).toContain('A'.repeat(64));
    expect(s.find('verifactu-record-previous').text()).toContain('B'.repeat(64));
    expect(s.find('verifactu-record-qr').attributes('src')).toBe(RECORD.qr_svg);
    const verify = s.find('verifactu-record-verify');
    expect([verify.attributes('href'), verify.attributes('target')]).toEqual([RECORD.qr_url, '_blank']);
    expect(s.find('verifactu-record-xml').text()).toContain('<soapenv:Envelope/>');
    expect(s.find('verifactu-record-digest').text()).toContain('Not stamped yet');
  });

  it('the first record of a chain says so; a record without its XML yet says it is built when it is sent', async () => {
    const s = await setup({ previous_fingerprint: '', envelope: '' });
    expect(s.find('verifactu-record-previous').text()).toContain('First record of the chain');
    const pending = s.find('verifactu-record-xml-pending').text();
    expect(pending).toBe('The XML is built when the record is sent to the AEAT.');
    expect(pending).not.toContain('producer');
  });

  it('in Spanish, the XML that is not built yet says it is built when it is sent', async () => {
    const s = await setup({ envelope: '' }, { locale: 'es' });
    const pending = s.find('verifactu-record-xml-pending').text();
    expect(pending).toBe('El XML se construye al enviar el registro a la AEAT.');
    expect(pending).not.toContain('productor');
  });

  it('«Send now» sends it and says what the AEAT answered', async () => {
    const s = await setup();
    s.answer(200, { chains: 1, sent: 1, accepted: 1, accepted_with_errors: 0, rejected: 0, waiting: 0, reason: '', message: '' });
    await click(s.find('verifactu-record-transmit').element);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/records/transmit', query: {}, body: { record_id: 'r1' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Sent: 1 accepted, 0 rejected, 0 waiting.');
  });

  it('a «Send now» that did not reach the AEAT is a warning in the server’s words, never a success', async () => {
    const s = await setup();
    s.answer(200, { chains: 0, sent: 0, accepted: 0, accepted_with_errors: 0, rejected: 0, waiting: 1, reason: 'unreachable', message: 'the gateway or the AEAT could not be reached (timeout)' });
    await click(s.find('verifactu-record-transmit').element);
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('the gateway or the AEAT could not be reached (timeout)', 'warning', 4500);
  });

  it('a refusal of «Send now» is said above the buttons, in the server’s words', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'verifactu.gateway_unavailable', message: 'It cannot be sent now.' } });
    await click(s.find('verifactu-record-transmit').element);
    expect(s.find('verifactu-record-error').text()).toBe('It cannot be sent now.');
  });

  it('«Correct» asks first and seals the correction', async () => {
    const s = await setup({ status: 'rejected', waiting: [], can_transmit: false, can_correct: true, can_cancel: false });
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, { record: { id: 'r3', invoice_number: 'TICKET-2026-000002' }, already: false });
    await click(s.find('verifactu-record-correct').element);
    expect(mocks.confirm.mock.calls[0][0].title).toBe('Correct the record of TICKET-2026-000002?');
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/records/correct', query: {}, body: { record_id: 'r1' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Correction of TICKET-2026-000002 sealed: it goes out with the next pass.');
  });

  it('«Ask the AEAT» takes it out of the queue when the AEAT already has it (VERIFACTU-F35)', async () => {
    const s = await setup();
    s.answer(200, { held: true, record: { id: 'r1', invoice_number: 'TICKET-2026-000002' } });
    await click(s.find('verifactu-record-ask').element);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/records/reconcile', query: {}, body: { record_id: 'r1' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('The AEAT already has TICKET-2026-000002: it is out of the queue.');
  });

  it('when the AEAT does not have it, «Ask the AEAT» says it stays in the queue, never a success', async () => {
    const s = await setup();
    s.answer(200, { held: false, record: { id: 'r1', invoice_number: 'TICKET-2026-000002' } });
    await click(s.find('verifactu-record-ask').element);
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(
      'The AEAT does not have TICKET-2026-000002: it stays in the queue and goes out with the next pass.',
      'warning',
      4500,
    );
  });

  it('a refusal of «Ask the AEAT» is said above the buttons, in the server’s words', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'verifactu.gateway_unavailable', message: 'The AEAT cannot be asked now.' } });
    await click(s.find('verifactu-record-ask').element);
    expect(s.find('verifactu-record-error').text()).toBe('The AEAT cannot be asked now.');
  });

  it('in Spanish, «Ask the AEAT» is «Preguntar a la AEAT»', async () => {
    const s = await setup({}, { locale: 'es' });
    expect(s.find('verifactu-record-ask').text()).toBe('Preguntar a la AEAT');
  });

  it('a record out of the queue has nothing to ask the AEAT', async () => {
    const s = await setup({ status: 'accepted', waiting: [], can_transmit: false });
    expect(s.find('verifactu-record-ask').exists()).toBe(false);
  });

  it('«Cancel record» opens its window', async () => {
    const s = await setup();
    await click(s.find('verifactu-record-cancel').element);
    expect(s.inDoc('verifactu-cancel')).not.toBeNull();
  });

  it('the employee only looks', async () => {
    const s = await setup({ can_correct: true }, { session: EMPLOYEE });
    for (const action of ['transmit', 'ask', 'correct', 'cancel']) expect(s.find(`verifactu-record-${action}`).exists()).toBe(false);
  });

  it('a record that does not exist says so, with Back', async () => {
    const m = await mountVerifactu(RecordDetailPage, { props: { id: 'nope' } });
    await m.live();
    m.net.lastStream().push(errorFrame(m.subId(OP), 'not_found'));
    await flush();
    expect(m.find('verifactu-record-not-found').text()).toContain('Record not found');
    expect(m.find('verifactu-record-back').exists()).toBe(true);
  });
});
