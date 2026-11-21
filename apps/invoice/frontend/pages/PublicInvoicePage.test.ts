import { AppPage, type SessionMe, toastError } from '@erplora/ui/shell';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import type { InvoiceOut } from '../operations';
import type { PublicTicketOut } from '../operations/public';
import { click, ionValue, mountInShell, overBase, settle } from '../__tests__/mount-invoice';
import PublicInvoicePage from './PublicInvoicePage.vue';

const mocks = vi.hoisted(() => ({ print: vi.fn() }));
vi.mock('../../../sale/frontend/lib/print', () => ({ printPaper: mocks.print }));

const VISITOR: SessionMe = { user: null, permissions: [], menu: [], apps: [], language: 'en' };
const CODE = '20261119-0001-K7Q2M9XD3FPA';
const TICKET: PublicTicketOut = {
  ticket: { number: 'TICKET-2026-000001', issue_date: '2026-11-19', total_amount: 1210, currency: 'EUR', issuer_name: 'Peluquería Ana' },
  invoice: null,
  record: null,
};
const INVOICE = {
  id: 'i1', number: 'FACT-2026-000001', invoice_type: 'F3', series_code: 'FACT', year: 2026,
  issue_date: '2026-11-19', issued_at: '2026-11-19T10:00:00Z', customer_name: 'Ana López',
  customer_tax_id: 'X1234567X', base_amount: 1000, tax_amount: 210, total_amount: 1210,
  currency: 'EUR', currency_decimals: 2, status: 'paid', source_type: 'substitution', rectifies_id: null,
  rectifies_number: '', substituted: false, can_mark_paid: false, can_rectify: true, can_substitute: false,
  series_id: 's1', sequence: 1, operation_date: '2026-11-19', issuer_name: 'Peluquería Ana',
  issuer_tax_id: 'B12345674', issuer_vat_number: 'B12345674', issuer_address: 'Calle Mayor 1', issuer_country: 'ES',
  customer_id: null, customer_address: 'Calle Sol 1', customer_country: '', customer_id_type: '',
  description: '', notes: '', tax_breakdown: [{ tax: 'vat', regime: '01', qualification: 'subject', exempt_reason: '', rate: '21.00', surcharge_rate: '0.00', base: 1000, quota: 210, surcharge_quota: 0 }],
  rectification_kind: '', sale_id: 'sale1', sale_number: '20261119-0001', refund_id: null, rectifies: null,
  substitutes: null, substituted_by: null, rectifications: [], remaining: 1210, paid_at: null, created_by: 'ticket code',
  lines: [{ id: 'l1', position: 1, description: 'Haircut', quantity: '1.000', unit_price: '1000.00', discount_amount: 0, tax_rate: '21.00', surcharge_rate: '0.00', tax_category_key: '', base_amount: 1000, tax_amount: 210, total_amount: 1210, product_id: null }],
} as InvoiceOut;
const RECORD = { qr_svg: 'data:image/svg+xml;base64,PHN2Zy8+', qr_url: 'https://prewww2.aeat.es/ValidarQR' };
const ISSUED = { issued: true, already: false, invoice: INVOICE, record: RECORD };
const DOOR = '/p/a/api/';

type Answer = [number, unknown] | 'hang';
let posted: { op: string; method: string; body: unknown }[] = [];

function door(answers: Record<string, Answer>): void {
  posted = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const op = url.startsWith(DOOR) ? url.slice(DOOR.length) : url;
    posted.push({ op, method: String(init.method), body: JSON.parse(String(init.body ?? 'null')) });
    const answer = answers[op];
    if (answer === 'hang') return new Promise<Response>(() => {});
    const [status, body] = answer ?? [404, { error: { code: 'not_found', message: 'Not found' } }];
    return Response.json(body, { status });
  }));
}

async function open(answers: Record<string, Answer> = { 'invoice.public.ticket': [200, TICKET] }, locale: 'en' | 'es' = 'en') {
  door(answers);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/p/:slug/invoice/:code', component: { template: '<div />' }, meta: { auth: false, chrome: false } }],
  });
  const m = await mountInShell(PublicInvoicePage, { path: `/p/a/invoice/${CODE}`, locale, session: VISITOR }, {
    path: `/p/a/invoice/${CODE}`, session: VISITOR, router, messages: overBase(en, es), inDocFrom: 'component',
  });
  await settle();
  await settle();
  const el = (testid: string) => m.inDoc(`invoice-public-${testid}`) as HTMLElement | null;
  return { ...m, el, text: () => m.wrapper.text() };
}

async function fill(s: Awaited<ReturnType<typeof open>>): Promise<void> {
  await ionValue(s.inDoc('invoice-recipient-name'), 'Ana López', 'ionInput');
  await ionValue(s.inDoc('invoice-recipient-tax-id'), 'X1234567X', 'ionInput');
  await ionValue(s.inDoc('invoice-recipient-address'), 'Calle Sol 1', 'ionInput');
}

async function submit(s: Awaited<ReturnType<typeof open>>): Promise<void> {
  const form = s.el('form');
  form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  await settle();
}

beforeEach(() => {
  document.cookie = 'hub_csrftoken=tok';
  const block = document.createElement('script');
  block.id = 'public-door';
  block.type = 'application/json';
  block.textContent = JSON.stringify({ currency: 'EUR', currency_decimals: 2 });
  document.body.append(block);
  mocks.print.mockReset();
});

afterEach(() => {
  document.getElementById('public-door')?.remove();
  vi.unstubAllGlobals();
});

describe('PublicInvoicePage', () => {
  it('opens the ticket through the public door and asks for the recipient without a customer search', async () => {
    const s = await open();
    expect(posted).toEqual([{ op: 'invoice.public.ticket', method: 'POST', body: { code: CODE } }]);
    expect(s.wrapper.findComponent(AppPage).props()).toMatchObject({ title: 'Request your invoice', contentLayout: 'detail' });
    expect(s.el('business')?.textContent).toContain('Peluquería Ana');
    expect(s.el('ticket')?.textContent).toContain('TICKET-2026-000001');
    expect(s.el('ticket')?.textContent).toContain('11/19/2026');
    expect(s.el('ticket')?.textContent).toContain('€12.10');
    expect(s.inDoc('invoice-recipient')).not.toBeNull();
    expect(s.wrapper.find('[data-testid=customer-search-trigger]').exists()).toBe(false);
    expect((s.el('submit') as { disabled?: boolean }).disabled).toBe(true);
    await submit(s);
    expect(posted.map(({ op }) => op)).toEqual(['invoice.public.ticket']);
  });

  it('says it is loading until the ticket answers', async () => {
    const s = await open({ 'invoice.public.ticket': 'hang' });
    expect(s.el('loading')?.textContent).toContain('Loading your ticket');
    expect(s.el('form')).toBeNull();
  });

  it('issues once with the code and the recipient, then shows the invoice and keeps its A4 with the QR to print', async () => {
    const s = await open({
      'invoice.public.ticket': [200, TICKET],
      'invoice.public.substitute': [200, ISSUED],
    });
    await fill(s);
    await submit(s);
    expect(posted[1]).toEqual({
      op: 'invoice.public.substitute', method: 'POST', body: {
        code: CODE, customer_name: 'Ana López', customer_country: '', customer_id_type: '',
        customer_tax_id: 'X1234567X', customer_address: 'Calle Sol 1',
      },
    });
    expect(s.el('ready')?.textContent).toContain('Your invoice is ready');
    expect(s.el('number')?.textContent).toContain('Invoice FACT-2026-000001');
    expect(s.el('invoice')?.textContent).toContain('Ana López');
    expect(s.el('invoice')?.textContent).toContain('X1234567X');
    expect(s.inDoc('invoice-detail-total')?.textContent).toContain('€12.10');
    expect(s.inDoc('invoice-paper')?.closest('[hidden]')).not.toBeNull();
    expect(s.inDoc('invoice-paper-number')?.textContent).toBe('FACT-2026-000001');
    expect(s.inDoc('invoice-paper-qr')?.querySelector('img')?.getAttribute('src')).toBe(RECORD.qr_svg);
    expect(s.el('form')).toBeNull();
    await submit(s);
    expect(posted).toHaveLength(2);
  });

  it('shows an invoice requested before without asking for the recipient or issuing again', async () => {
    const s = await open({ 'invoice.public.ticket': [200, { ...TICKET, invoice: INVOICE, record: RECORD }] });
    expect(s.el('already')?.textContent).toContain('already requested');
    expect(s.el('number')?.textContent).toContain('Invoice FACT-2026-000001');
    expect(s.inDoc('invoice-paper-number')?.textContent).toBe('FACT-2026-000001');
    expect(s.inDoc('invoice-recipient')).toBeNull();
    expect(posted.map(({ op }) => op)).toEqual(['invoice.public.ticket']);
  });

  it.each([
    [404, 'invoice.code_not_found', 'This code opens no ticket.', false],
    [410, 'invoice.code_expired', 'This code has expired.', false],
    [409, 'invoice.ticket_pending', 'Your ticket is still being registered.', true],
  ])('says plainly why a ticket cannot open, with «Retry» only where it can change it (%i %s)', async (status, code, message, retry) => {
    const s = await open({ 'invoice.public.ticket': [status, { error: { code, message } }] });
    expect(s.el('error')?.textContent).toContain(message);
    expect(s.el('retry') !== null).toBe(retry);
    expect(s.el('form')).toBeNull();
  });

  it('a connection over the limit reads the server’s words and may try again', async () => {
    const message = 'Too many requests. Try again in a moment.';
    const s = await open({ 'invoice.public.ticket': [429, { error: { code: 'base.rate_limited', message } }] });
    expect(s.el('error')?.textContent).toContain(message);
    expect(s.el('retry')).not.toBeNull();
    expect(s.el('ticket')).toBeNull();
  });

  it('a failure the server did not word says the page’s own sentence, with «Retry»', async () => {
    const s = await open({ 'invoice.public.ticket': [500, { error: { code: 'internal_error', message: 'Internal error' } }] });
    expect(s.el('error')?.textContent).toContain('The ticket could not be loaded. Try again.');
    expect(s.el('retry')).not.toBeNull();
  });

  it('retries a pending ticket when the customer asks', async () => {
    const answers: Record<string, Answer> = {
      'invoice.public.ticket': [409, { error: { code: 'invoice.ticket_pending', message: 'Your ticket is still being registered.' } }],
    };
    const s = await open(answers);
    answers['invoice.public.ticket'] = [200, TICKET];
    await click(s.el('retry'));
    expect(s.el('ticket')?.textContent).toContain('TICKET-2026-000001');
    expect(posted.map(({ op }) => op)).toEqual(['invoice.public.ticket', 'invoice.public.ticket']);
  });

  it.each([422, 409])('puts a refused field under it and clears it when corrected (%i)', async (status) => {
    const s = await open({
      'invoice.public.ticket': [200, TICKET],
      'invoice.public.substitute': [status, { error: { code: status === 409 ? 'invoice.recipient_incomplete' : 'validation_error', message: 'Check the recipient.', fields: { customer_tax_id: 'That tax ID is not valid.' } } }],
    });
    await fill(s);
    await submit(s);
    expect((s.inDoc('invoice-recipient-tax-id') as { errorText?: string }).errorText).toBe('That tax ID is not valid.');
    expect(s.el('form-error')?.textContent).toContain('Check the recipient.');
    await ionValue(s.inDoc('invoice-recipient-tax-id'), 'Y1234567X', 'ionInput');
    expect((s.inDoc('invoice-recipient-tax-id') as { errorText?: string }).errorText).toBe('');
    expect(s.el('form-error')).toBeNull();
  });

  it('a refusal while issuing keeps what was typed and reads the server’s words', async () => {
    const message = 'Too many requests. Try again in a moment.';
    const s = await open({
      'invoice.public.ticket': [200, TICKET],
      'invoice.public.substitute': [429, { error: { code: 'base.rate_limited', message } }],
    });
    await fill(s);
    await submit(s);
    expect(s.el('form-error')?.textContent).toContain(message);
    expect((s.inDoc('invoice-recipient-name') as { value?: string }).value).toBe('Ana López');
  });

  it('prints the issued paper with its invoice number', async () => {
    const s = await open({ 'invoice.public.ticket': [200, { ...TICKET, invoice: INVOICE, record: RECORD }] });
    await click(s.el('print'));
    expect(mocks.print).toHaveBeenCalledOnce();
    expect(mocks.print.mock.calls[0][1]).toEqual({ title: 'Invoice FACT-2026-000001' });
  });

  it('a print the browser refused says so in a toast', async () => {
    mocks.print.mockRejectedValueOnce(new Error('blocked'));
    const s = await open({ 'invoice.public.ticket': [200, { ...TICKET, invoice: INVOICE, record: RECORD }] });
    await click(s.el('print'));
    await settle();
    expect(toastError).toHaveBeenCalledWith('Could not print the invoice');
  });

  it('speaks Spanish', async () => {
    const s = await open(undefined, 'es');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Solicita tu factura');
    const labels = [...(s.el('ticket')?.querySelectorAll('ion-label') ?? [])].map((label) => label.innerHTML);
    expect(s.el('ticket-number')?.textContent?.trim()).toBe('Tique TICKET-2026-000001');
    expect(labels).toEqual(['Negocio', 'Fecha', 'Total']);
    expect(s.el('ticket')?.textContent).toContain('12,10');
    expect(s.el('submit')?.textContent).toContain('Solicitar factura completa');
  });
});
