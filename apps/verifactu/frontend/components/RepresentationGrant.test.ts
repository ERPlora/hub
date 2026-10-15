// «ERPlora files for you» → the representation authorisation (Anexo I of Convenio 17; VERIFACTU-F05, F06), as the
// old module's `erp-verifactu-grant` (`erp-verifactu-grant.test.ts`, `grant-resubmit.test.ts`): its state first, in
// plain words and with its tone; what was sent and its steps; «Send again» while it is under review or in force; and,
// when there is something to do, the procedure: the blank official model to download, who signs (a self-employed
// business signs itself; a company names its legal representative), the data-protection essentials BEFORE any identity
// document is asked, and the two to four PDFs to upload («Send for review»). A refusal is said by its code. The
// taxpayer is Invoicing's issuer, read and never asked here. Only who configures VeriFactu sends it.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, ionValue, mountVerifactu, settle } from '../__tests__/mount-verifactu';
import { saveBase64File } from '../lib/files';
import type { ConfigOut, RepresentationOut } from '../operations';
import RepresentationGrant from './RepresentationGrant.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
vi.mock('../lib/files', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  saveBase64File: vi.fn(),
}));
beforeEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(saveBase64File).mockClear();
});

const NONE: RepresentationOut = {
  status: 'none',
  updated_at: null,
  reason: '',
  linked: true,
  company: true,
  submission: null,
  history: [],
};

const CONFIG = {
  environment: 'testing',
  route: 'erplora',
  issuer_nif: 'B12345674',
  issuer_name: 'Peluquería Ana SL',
  representation: NONE,
} as ConfigOut;

const SUBMISSION: RepresentationOut['submission'] = {
  version: 2,
  submitted_at: '2026-10-15T10:00:00Z',
  document_type: 'dni',
  documents: ['signed_model', 'id_copy', 'representation_proof'],
};

async function setup(representation: Partial<RepresentationOut> = {}, options: { locale?: 'en' | 'es'; canConfigure?: boolean; config?: Partial<ConfigOut> } = {}) {
  const config = { ...CONFIG, ...options.config, representation: { ...NONE, ...representation } };
  const m = await mountVerifactu(RepresentationGrant, {
    path: '/verifactu/config',
    locale: options.locale,
    session: options.canConfigure === false ? EMPLOYEE : undefined,
    props: { config, canConfigure: options.canConfigure ?? true },
  });
  await settle();
  return m;
}

type Mounted = Awaited<ReturnType<typeof setup>>;

const pdf = (name: string, size = 12) => new File([new Uint8Array(size).fill(0x25)], name, { type: 'application/pdf' });

/** Picks `file` in the document's file input, as the browser's picker does. */
async function pick(m: Mounted, document: string, file: File): Promise<void> {
  const input = m.wrapper.get(`[data-testid="verifactu-grant-file-${document}"]`);
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
  await input.trigger('change');
  await settle();
}

const submitDisabled = (m: Mounted) => (m.find('verifactu-grant-submit').element as HTMLElement & { disabled?: boolean }).disabled === true;

describe('the state, before anything', () => {
  it('without an authorisation it says so and offers the procedure', async () => {
    const s = await setup();
    expect(s.find('verifactu-config-grant').text()).toBe('Not signed. Your business cannot go live through ERPlora until you sign it.');
    expect(s.find('verifactu-config-grant').attributes('data-tone')).toBe('warning');
    expect(s.find('verifactu-grant-form').exists()).toBe(true);
  });

  it('approved asks for nothing', async () => {
    const s = await setup({ status: 'approved', updated_at: '2026-10-02T10:00:00Z' });
    expect(s.find('verifactu-config-grant').text()).toContain('ERPlora can file on your behalf.');
    expect(s.find('verifactu-config-grant').attributes('data-tone')).toBe('success');
    expect(s.find('verifactu-grant-form').exists()).toBe(false);
  });

  it('under review asks for nothing either', async () => {
    const s = await setup({ status: 'submitted', updated_at: '2026-10-02T10:00:00Z' });
    expect(s.find('verifactu-config-grant').text()).toContain('Under review since');
    expect(s.find('verifactu-config-grant').attributes('data-tone')).toBe('info');
    expect(s.find('verifactu-grant-form').exists()).toBe(false);
  });

  it('returned shows the reason, the one thing to act on, with the form already open', async () => {
    const s = await setup({ status: 'returned', updated_at: '2026-10-02T10:00:00Z', reason: 'Unsigned page 2' });
    expect(s.find('verifactu-config-grant').attributes('data-tone')).toBe('danger');
    expect(s.find('verifactu-config-grant-reason').text()).toBe('Note of the review: Unsigned page 2');
    expect(s.find('verifactu-grant-form').exists()).toBe(true);
    expect(s.find('verifactu-grant-resend').exists()).toBe(false);
  });

  it('revoked says so and offers the procedure again', async () => {
    const s = await setup({ status: 'revoked', updated_at: '2026-10-02T10:00:00Z' });
    expect(s.find('verifactu-config-grant').attributes('data-tone')).toBe('danger');
    expect(s.find('verifactu-grant-form').exists()).toBe(true);
  });
});

describe('the business is not asked here', () => {
  it('the taxpayer is Invoicing’s issuer, read and not typed', async () => {
    const s = await setup();
    expect(s.find('verifactu-grant-taxpayer').text()).toBe('Taxpayer: Peluquería Ana SL (B12345674), Invoicing’s issuer.');
  });

  it('without Invoicing’s issuer it says where to set it up and does not send', async () => {
    const s = await setup({}, { config: { issuer_nif: '', issuer_name: '' } });
    expect(s.find('verifactu-grant-issuer-missing').text()).toBe('Set up the issuer first in Invoicing → Issuer: it is who owes the tax.');
    expect(submitDisabled(s)).toBe(true);
  });

  it('while ERPlora has not linked the business it says so and does not send', async () => {
    const s = await setup({ linked: false });
    expect(s.find('verifactu-grant-not-linked').text()).toBe('ERPlora has not linked this business yet: you can send it once your ERPlora account has sent its data.');
    await pick(s, 'signed_model', pdf('model.pdf'));
    await pick(s, 'id_copy', pdf('dni.pdf'));
    await pick(s, 'representation_proof', pdf('deeds.pdf'));
    expect(submitDisabled(s)).toBe(true);
  });
});

describe('who signs depends on what the business is', () => {
  it('a self-employed business signs itself: no legal representative and no proof are asked', async () => {
    const s = await setup({ company: false }, { config: { issuer_nif: '12345678Z', issuer_name: 'Ana Pérez' } });
    expect(s.find('verifactu-grant-legal-representative').exists()).toBe(false);
    expect(s.find('verifactu-grant-signer-name').exists()).toBe(false);
    expect(s.find('verifactu-grant-choose-representation_proof').exists()).toBe(false);
    await pick(s, 'signed_model', pdf('model.pdf'));
    await pick(s, 'id_copy', pdf('dni.pdf'));
    s.answer(201, { ...CONFIG, representation: { ...NONE, company: false, status: 'submitted' } });
    await click(s.find('verifactu-grant-submit').element);
    await settle();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/verifactu/representation',
        query: {},
        body: { signer_document_type: 'dni', signed_model_base64: 'JSUlJSUlJSUlJSUl', id_copy_base64: 'JSUlJSUlJSUlJSUl' },
      },
    ]);
  });

  it('a company asks its legal representative and the proof of representation', async () => {
    const s = await setup();
    expect(s.find('verifactu-grant-legal-representative').text()).toBe('Legal representative');
    expect(s.find('verifactu-grant-signer-name').exists()).toBe(true);
    expect(s.find('verifactu-grant-signer-nif').exists()).toBe(true);
    expect(s.find('verifactu-grant-representation-proof-why').text()).toBe('Your business is a company, so we need the document that names the person allowed to sign for it.');
  });

  it('the signature sample only appears with a NIE', async () => {
    const s = await setup();
    expect(s.find('verifactu-grant-choose-signature_sample').exists()).toBe(false);
    await ionValue(s.find('verifactu-grant-document-type').element, 'nie');
    expect(s.find('verifactu-grant-signature-sample-why').text()).toBe('A NIE often carries no printed signature, so we need a sheet with your handwritten signature to compare it against.');
    expect(s.find('verifactu-grant-choose-signature_sample').exists()).toBe(true);
  });
});

describe('the attachments', () => {
  it('«Attach…» opens the file picker of its own document', async () => {
    const s = await setup();
    const opened: string[] = [];
    const spy = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function (this: HTMLInputElement) {
      opened.push(this.dataset.testid ?? '');
    });
    await click(s.find('verifactu-grant-choose-id_copy').element);
    spy.mockRestore();
    expect(opened).toEqual(['verifactu-grant-file-id_copy']);
  });

  it('each one takes a PDF', async () => {
    const s = await setup();
    for (const document of ['signed_model', 'id_copy', 'representation_proof']) {
      expect(s.find(`verifactu-grant-file-${document}`).attributes('accept')).toBe('.pdf,application/pdf');
    }
  });

  it('sending needs the signed model, the identity copy and, for a company, its representative and the proof', async () => {
    const s = await setup();
    expect(submitDisabled(s)).toBe(true);
    await pick(s, 'signed_model', pdf('model.pdf'));
    await pick(s, 'id_copy', pdf('dni.pdf'));
    expect(submitDisabled(s)).toBe(true);
    await pick(s, 'representation_proof', pdf('deeds.pdf'));
    expect(submitDisabled(s)).toBe(true);
    await ionValue(s.find('verifactu-grant-signer-name').element, 'Ana Pérez', 'ionInput');
    await ionValue(s.find('verifactu-grant-signer-nif').element, '12345678Z', 'ionInput');
    expect(submitDisabled(s)).toBe(false);
  });

  it('removing a file really removes it: sending is blocked again', async () => {
    const s = await setup({ company: false });
    await pick(s, 'signed_model', pdf('model.pdf'));
    await pick(s, 'id_copy', pdf('dni.pdf'));
    expect(s.find('verifactu-grant-picked-signed_model').text()).toContain('model.pdf');
    expect(submitDisabled(s)).toBe(false);
    await click(s.find('verifactu-grant-remove-signed_model').element);
    expect(s.find('verifactu-grant-picked-signed_model').exists()).toBe(false);
    expect(submitDisabled(s)).toBe(true);
  });

  it('a file over 5 MB is said before it is sent', async () => {
    const s = await setup({ company: false });
    await pick(s, 'signed_model', pdf('scan.pdf', 5 * 1024 * 1024 + 1));
    expect(s.find('verifactu-grant-error').text()).toBe('Each file has to be 5 MB at most.');
    expect(s.find('verifactu-grant-picked-signed_model').exists()).toBe(false);
    expect(s.sent()).toEqual([]);
  });
});

describe('a refusal says why, by its code', () => {
  async function refusedWith(error: Record<string, unknown>, status = 422) {
    const s = await setup({ company: false });
    await pick(s, 'signed_model', pdf('model.pdf'));
    await pick(s, 'id_copy', pdf('dni.pdf'));
    s.answer(status, { error });
    await click(s.find('verifactu-grant-submit').element);
    await settle();
    return s;
  }

  it('the SaaS’s code is said in the person’s words', async () => {
    const s = await refusedWith({ code: 'fiscal.id_copy_required', message: 'Invalid payload', fields: { 'documents.id_copy': 'Attach…' } });
    expect(s.find('verifactu-grant-error').text()).toBe('Attach a copy of the identity document.');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('without ERPlora it says to try again in a few minutes', async () => {
    const s = await refusedWith({ code: 'verifactu.saas_unreachable', message: 'x' }, 503);
    expect(s.find('verifactu-grant-error').text()).toBe('ERPlora could not handle this right now. Try again in a few minutes.');
  });

  it('a code it does not know is not silenced: the server’s words, or that it did not work', async () => {
    const s = await refusedWith({ code: 'fiscal.something_new', message: 'Something new went wrong.' });
    expect(s.find('verifactu-grant-error').text()).toBe('Something new went wrong.');
  });
});

describe('the blank model', () => {
  it('is downloaded from ERPlora and handed to the browser', async () => {
    const s = await setup();
    s.answer(200, { filename: 'anexo-i.pdf', content_type: 'application/pdf', content_base64: 'JVBERi0xLjQ=' });
    await click(s.find('verifactu-grant-download').element);
    await settle();
    expect(s.sent()).toEqual([{ method: 'GET', path: '/api/verifactu/representation/model', query: {}, body: undefined }]);
    expect(saveBase64File).toHaveBeenCalledWith('anexo-i.pdf', 'application/pdf', 'JVBERi0xLjQ=');
    expect(s.find('verifactu-grant-downloaded').text()).toBe('Model downloaded. Sign it and upload it below.');
  });

  it('without ERPlora it says why', async () => {
    const s = await setup();
    s.answer(503, { error: { code: 'verifactu.saas_unreachable', message: 'x' } });
    await click(s.find('verifactu-grant-download').element);
    await settle();
    expect(saveBase64File).not.toHaveBeenCalled();
    expect(s.find('verifactu-grant-error').text()).toBe('ERPlora could not handle this right now. Try again in a few minutes.');
  });
});

describe('what the law asks before an identity document', () => {
  it('the data-protection essentials (art. 13 GDPR) come before the uploads', async () => {
    const s = await setup();
    const html = s.wrapper.html();
    expect(s.find('verifactu-grant-privacy').text()).toContain('ERPLORA CLOUD SL (B27593136)');
    expect(html.indexOf('data-testid="verifactu-grant-privacy"')).toBeLessThan(html.indexOf('data-testid="verifactu-grant-choose-id_copy"'));
  });
});

describe('what was sent', () => {
  it('names the submission number, its date and the documents sent', async () => {
    const s = await setup({ status: 'submitted', updated_at: '2026-10-15T10:00:00Z', submission: SUBMISSION });
    expect(s.find('verifactu-grant-submitted').text()).toContain('Submission no. 2, sent on');
    expect(s.find('verifactu-grant-doc-signed_model').text()).toBe('Signed model');
    expect(s.find('verifactu-grant-doc-id_copy').text()).toBe('Copy of the identity document');
    expect(s.find('verifactu-grant-doc-representation_proof').text()).toBe('Proof of representation');
    expect(s.find('verifactu-grant-doc-signature_sample').exists()).toBe(false);
  });

  it('lists its steps with their outcome and the reason', async () => {
    const s = await setup({
      status: 'returned',
      submission: SUBMISSION,
      history: [
        { status: 'returned', at: '2026-10-16T10:00:00Z', version: null, reason: 'Blurry ID' },
        { status: 'submitted', at: '2026-10-15T10:00:00Z', version: 2, reason: '' },
      ],
    });
    const rows = s.wrapper.findAll('[data-testid="verifactu-grant-history-row"]').map((row) => row.text());
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain('Returned');
    expect(rows[0]).toContain('Blurry ID');
    expect(rows[1]).toContain('Sent for review (no. 2)');
  });

  it('with nothing sent there is no «what you sent» and no history', async () => {
    const s = await setup();
    expect(s.find('verifactu-grant-submitted').exists()).toBe(false);
    expect(s.find('verifactu-grant-history').exists()).toBe(false);
  });
});

describe('sending again', () => {
  it('under review, «Send again» opens the form and says the new one replaces it', async () => {
    const s = await setup({ status: 'submitted', submission: SUBMISSION });
    await click(s.find('verifactu-grant-resend').element);
    expect(s.find('verifactu-grant-resend-hint').text()).toBe('If something came out wrong, send it again: the new submission replaces the one under review.');
    expect(s.find('verifactu-grant-form').exists()).toBe(true);
    await click(s.find('verifactu-grant-resend-cancel').element);
    expect(s.find('verifactu-grant-form').exists()).toBe(false);
  });

  it('in force it also lets you send again, saying the current one keeps filing meanwhile', async () => {
    const s = await setup({ status: 'approved', submission: SUBMISSION });
    await click(s.find('verifactu-grant-resend').element);
    expect(s.find('verifactu-grant-resend-hint').text()).toBe('While we review the new submission, you keep filing with the current one.');
  });

  it('after sending, it says so, shows what was sent and closes the form', async () => {
    const s = await setup({ status: 'returned', reason: 'Blurry ID', company: false });
    await pick(s, 'signed_model', pdf('model.pdf'));
    await pick(s, 'id_copy', pdf('dni.pdf'));
    s.answer(201, { ...CONFIG, representation: { ...NONE, company: false, status: 'submitted', updated_at: '2026-10-15T10:00:00Z', submission: SUBMISSION } });
    await click(s.find('verifactu-grant-submit').element);
    await settle();
    expect(toastSuccess).toHaveBeenCalledWith('Sent for review. We let you know by email within 24-72 hours.');
    expect(s.find('verifactu-grant-form').exists()).toBe(false);
    expect(s.find('verifactu-grant-submitted').exists()).toBe(true);
  });
});

describe('who does not configure VeriFactu', () => {
  it('sees the state and cannot send', async () => {
    const s = await setup({}, { canConfigure: false });
    expect(s.find('verifactu-config-grant').exists()).toBe(true);
    expect(s.find('verifactu-grant-form').exists()).toBe(false);
  });
});

describe('Spanish', () => {
  it('speaks it, with «otorgamiento de representación»', async () => {
    const s = await setup({}, { locale: 'es' });
    expect(s.find('verifactu-grant-intro').text()).toContain('ERPlora remite tus registros de facturación a la Agencia Tributaria EN TU NOMBRE.');
    expect(s.find('verifactu-grant-download').text()).toBe('Descargar el modelo');
    expect(s.find('verifactu-grant-submit').text()).toBe('Enviar a revisión');
    expect(s.wrapper.html()).not.toMatch(/apoderamiento/i);
  });
});
