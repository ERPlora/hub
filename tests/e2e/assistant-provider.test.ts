// @vitest-environment node
// The assistant's e2e provider (assistant-provider.ts): it answers as OpenAI streams — text in pieces, a tool call in
// fragments with `finish_reason: tool_calls`, then the usage —, by the marker of the question, and tells the outcome
// of a tool once its result comes back; all of it in the language the Hub's system message asks for (hub#1025).
import { request } from 'node:http';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import {
  answerTo,
  CANNOT_RECTIFY,
  CLAIM_ANSWER,
  closeCashSummary,
  DICTATION,
  DONE,
  FORMAT_ANSWER,
  GREETING,
  LANGUAGES,
  languageOf,
  NO_REASON,
  NOT_DONE,
  type Provider,
  rectifyPreview,
  SLOW_ANSWER,
  startProvider,
  STEPS_SAID,
} from './assistant-provider';

type Frame = { choices: { delta: { content?: string; tool_calls?: { function: { name?: string; arguments?: string } }[] }; finish_reason: string | null }[] };

const textOf = (frames: unknown[]) =>
  (frames as Frame[]).flatMap((frame) => frame.choices.map((choice) => choice.delta.content ?? '')).join('');
const finish = (frames: unknown[]) => (frames as Frame[]).flatMap((frame) => frame.choices.map((c) => c.finish_reason)).filter(Boolean);
const toolOf = (frames: unknown[]) => {
  const pieces = (frames as Frame[]).flatMap((frame) => frame.choices.flatMap((c) => c.delta.tool_calls ?? []));
  return { name: pieces.map((p) => p.function.name ?? '').join(''), arguments: pieces.map((p) => p.function.arguments ?? '').join('') };
};
const user = (content: string) => ({ role: 'user', content });

/** The Hub's system message of a turn whose person reads `name` (base/assistant.py `instructions`: «Answer in <the
 *  name of their language>, …»), as erplora.com's gateway forwards it, its own rules after it. */
const system = (name: string) => ({
  role: 'system',
  content: `You are the assistant of the business «E2E» in ERPlora, its point of sale and management app.\nAnswer in ${name}, short and plain, as a colleague who knows the app.\n\n- Only help with this business and with using ERPlora.`,
});
const IN = { en: system('English'), es: system('Spanish') } as const;
const requested = (name: string) => ({ role: 'assistant', content: '', tool_calls: [{ function: { name } }] });
const NOT_CONFIRMED = { role: 'tool', content: '{"error": {"code": "base.assistant_not_confirmed", "message": "Not confirmed."}}' };
const SUMMARY = {
  number: 'S-1',
  closing_balance: 25000,
  expected_balance: 23000,
  difference: 2000,
  expected_hidden: false,
  pending: { open_checks: 0, open_check_labels: [], unserved: 0, unserved_labels: [], prints: 0, print_usages: [], incomplete: false },
};
const PREVIEW = {
  original: { number: 'F-1', issue_date: '2026-10-26', customer_name: 'Talleres Pérez SL', total_amount: 12100, remaining: 12100 },
  invoice_type: 'R1',
  reason: 'el precio estaba mal',
  series_code: 'RECT',
  next_number: 'RECT-2026-000001',
  issue_date: '2026-10-27',
  whole: true,
  base_amount: -10000,
  tax_amount: -2100,
  total_amount: -12100,
  lines: [{ description: 'Corte', quantity: '-1.000', total_amount: -12100 }],
};

describe('answerTo', () => {
  it('a question without a marker: the greeting, streamed in pieces, ending in «stop»', () => {
    const answer = answerTo([user('hola')]);
    expect(textOf(answer.frames)).toBe(GREETING.en);
    expect(answer.frames.length).toBeGreaterThan(3);
    expect(finish(answer.frames)).toEqual(['stop']);
  });

  it('the format, the claim and a slow answer by their markers', () => {
    expect(textOf(answerTo([user('E2E-FORMAT')]).frames)).toBe(FORMAT_ANSWER.en);
    expect(textOf(answerTo([user('E2E-CLAIM')]).frames)).toBe(CLAIM_ANSWER.en);
    expect(answerTo([user('E2E-SLOW')]).delayMs).toBeGreaterThan(0);
    expect(answerTo([user('E2E-DOWN')]).status).toBe(500);
  });

  it('a write: the tool call in fragments; then, with its result, the outcome', () => {
    const asked = answerTo([user('E2E-CREATE Mesa 4')]);
    expect(toolOf(asked.frames)).toEqual({ name: 'demo__item__create', arguments: '{"name":"Mesa 4"}' });
    expect(finish(asked.frames)).toEqual(['tool_calls']);
    expect(toolOf(answerTo([user('E2E-DELETE abc')]).frames)).toEqual({ name: 'demo__item__delete', arguments: '{"id":"abc"}' });
    expect(textOf(answerTo([user('x'), { role: 'tool', content: '{"id": "1"}' }]).frames)).toBe(DONE.en);
    expect(textOf(answerTo([user('x'), { role: 'tool', content: '{"error": {"code": "base.assistant_not_confirmed"}}' }]).frames)).toBe(NOT_DONE.en);
  });

  it('any write the spec names, with its data as written (E2E-ASK): the tool call in fragments; then the outcome', () => {
    const question = user('E2E-ASK base__access__settings_update {"pin_inactivity_minutes":10,"pin_length":6}');
    const asked = answerTo([question]);
    expect(toolOf(asked.frames)).toEqual({
      name: 'base__access__settings_update',
      arguments: '{"pin_inactivity_minutes":10,"pin_length":6}',
    });
    expect(finish(asked.frames)).toEqual(['tool_calls']);
    const cancelled = [question, { role: 'tool', content: '{"error": {"code": "base.assistant_not_confirmed"}}' }];
    expect(textOf(answerTo(cancelled).frames)).toBe(NOT_DONE.en);
  });

  it('a list it offers (E2E-OFFER), one line per « | », as text; the write named in it, only when the next question hears that list', () => {
    const offer = 'E2E-OFFER 1. Saturday at 20:00 | 2. Saturday at 21:30 | E2E-ASK reservation__reservation__create {"time":"21:30"}';
    const offered = answerTo([user(`A table for 4 on Saturday?\n${offer}`)]);
    const list = '1. Saturday at 20:00\n2. Saturday at 21:30\nE2E-ASK reservation__reservation__create {"time":"21:30"}';
    expect(textOf(offered.frames)).toBe(list);
    expect(finish(offered.frames)).toEqual(['stop']);
    // WHATSAPP_INBOX-F19: the guest's «the 2nd» comes with what the business last wrote them, the list: its write is asked.
    const picked = answerTo([user(`———\nthe 2nd\n———\n\n———\n${list}\n———\n`)]);
    expect(toolOf(picked.frames)).toEqual({ name: 'reservation__reservation__create', arguments: '{"time":"21:30"}' });
  });

  it('the outcome by the shape of the result: the Hub’s error envelope is a refusal, a word inside a result that ran is not', () => {
    const outcome = (content: string) => textOf(answerTo([user('x'), { role: 'tool', content }]).frames);
    // What the Hub sends when a tool did not run (`error_content`): cancelled, refused, failed with its fields.
    for (const code of ['base.assistant_not_confirmed', 'permission_denied', 'app_inactive', 'requires_elevation'])
      expect(outcome(JSON.stringify({ error: { code, message: 'No.' } })), code).toBe(NOT_DONE.en);
    expect(outcome(JSON.stringify({ error: { code: 'invalid_payload', message: 'Some data does not fit.', fields: { name: 'Required' } } }))).toBe(NOT_DONE.en);
    // A print job that ran: its row says it can be cancelled, and was not; it carries no error.
    const job = { id: '1', status: 'pending', cancellable: true, cancelled_at: null, cancel_reason: '', last_error: '', retryable: true };
    expect(outcome(JSON.stringify({ job, duplicate: false, skipped: null }))).toBe(DONE.en);
    expect(outcome(JSON.stringify({ status: 'refused_by_customer', denied: 0, error_count: 0 }))).toBe(DONE.en);
    // A result too long for the model, cut by the Hub (` …(cut)`): it ran.
    expect(outcome(`${JSON.stringify({ rows: [{ status: 'cancelled' }] })} …(cut)`)).toBe(DONE.en);
  });

  it('a chain: first a read, then a write, then the outcome', () => {
    const question = user('E2E-CHAIN Mesa 7');
    const asked = (name: string) => ({ role: 'assistant', content: '', tool_calls: [{ function: { name } }] });
    expect(toolOf(answerTo([question]).frames)).toEqual({ name: 'demo__item__list', arguments: '{}' });
    const read = [question, asked('demo__item__list'), { role: 'tool', content: '{"rows": []}' }];
    expect(toolOf(answerTo(read).frames)).toEqual({ name: 'demo__item__create', arguments: '{"name":"Mesa 7"}' });
    const written = [...read, asked('demo__item__create'), { role: 'tool', content: '{"id": "1"}' }];
    expect(textOf(answerTo(written).frames)).toBe(DONE.en);
  });

  it('a chain that speaks in every round (BASE-F101): its words before the read, before the write, then the outcome', () => {
    const question = user('E2E-STEPS Mesa 7');
    const asked = (name: string) => ({ role: 'assistant', content: '', tool_calls: [{ function: { name } }] });
    const first = answerTo([question]).frames;
    expect(textOf(first)).toBe(STEPS_SAID.en[0]);
    expect(toolOf(first)).toEqual({ name: 'demo__item__list', arguments: '{}' });
    const read = [question, asked('demo__item__list'), { role: 'tool', content: '{"rows": []}' }];
    const second = answerTo(read).frames;
    expect(textOf(second)).toBe(STEPS_SAID.en[1]);
    expect(toolOf(second)).toEqual({ name: 'demo__item__create', arguments: '{"name":"Mesa 7"}' });
    const cancelled = [...read, asked('demo__item__create'), { role: 'tool', content: '{"error": {"code": "base.assistant_not_confirmed"}}' }];
    expect(textOf(answerTo(cancelled).frames)).toBe(NOT_DONE.en);
  });

  it('closing the drawer (CASH_REGISTER-F09): the summary first, then its words and the close of that session, then the outcome', () => {
    const question = user('E2E-CLOSE-CASH 25000');
    const asked = (name: string) => ({ role: 'assistant', content: '', tool_calls: [{ function: { name } }] });
    expect(toolOf(answerTo([question]).frames)).toEqual({
      name: 'cash_register__session__closing_summary',
      arguments: '{"closing_balance":25000}',
    });
    const summary = {
      number: 'S-261024-0001',
      closing_balance: 25000,
      expected_balance: 23000,
      difference: 2000,
      expected_hidden: false,
      pending: { open_checks: 2, open_check_labels: ['Mesa 4', 'Mesa 7'], unserved: 0, unserved_labels: [], prints: 0, print_usages: [], incomplete: false },
    };
    const read = [question, asked('cash_register__session__closing_summary'), { role: 'tool', content: JSON.stringify(summary) }];
    const close = answerTo(read);
    // The summary is said before the card, in the same answer that asks for the close of exactly that session.
    expect(textOf(close.frames)).toBe(closeCashSummary(summary, 'en'));
    expect(toolOf(close.frames)).toEqual({
      name: 'cash_register__session__close',
      arguments: '{"session":"S-261024-0001","closing_balance":25000}',
    });
    expect(finish(close.frames)).toEqual(['tool_calls']);
    const closed = [...read, asked('cash_register__session__close'), { role: 'tool', content: '{"status": "closed"}' }];
    expect(textOf(answerTo(closed).frames)).toBe(DONE.en);
    // Asked again in the same conversation (after a «Cancel»): the summary again, read now, never the old one.
    const again = [...closed, { role: 'assistant', content: DONE.en }, question];
    expect(toolOf(answerTo(again).frames).name).toBe('cash_register__session__closing_summary');
    const readAgain = [...again, asked('cash_register__session__closing_summary'), { role: 'tool', content: JSON.stringify({ ...summary, number: 'S-261024-0002' }) }];
    expect(toolOf(answerTo(readAgain).frames).arguments).toBe('{"session":"S-261024-0002","closing_balance":25000}');
    // A summary refused (the count required and not said, no open session): it is said, and nothing is asked for.
    const refused = [question, asked('cash_register__session__closing_summary'), { role: 'tool', content: '{"error": {"code": "cash_register.no_open_session"}}' }];
    expect(toolOf(answerTo(refused).frames).name).toBe('');
    expect(textOf(answerTo(refused).frames)).toBe(NOT_DONE.en);
  });

  it('the close summary as the model says it in Spanish: the expected and the difference only when they came, and what is pending', () => {
    const base = { number: 'S-1', closing_balance: 25000, pending: { open_checks: 0, open_check_labels: [], unserved: 0, unserved_labels: [], prints: 0, print_usages: [], incomplete: false } };
    expect(closeCashSummary({ ...base, expected_balance: 23000, difference: 2000, expected_hidden: false }, 'es')).toBe(
      'Vas a cerrar la sesión **S-1**:\n\n- Contado: 250.00 €\n- Esperado: 230.00 €\n- Diferencia: +20.00 €',
    );
    expect(closeCashSummary({ ...base, expected_balance: 23000, difference: -500, expected_hidden: false }, 'es')).toContain('- Diferencia: -5.00 €');
    const blind = closeCashSummary({ ...base, expected_balance: null, difference: null, expected_hidden: true }, 'es');
    expect(blind).toBe('Vas a cerrar la sesión **S-1**:\n\n- Contado: 250.00 €\n- Arqueo ciego: el cierre lo comparará al confirmar.');
    const pending = closeCashSummary(
      {
        ...base,
        expected_balance: null,
        difference: null,
        expected_hidden: true,
        pending: { open_checks: 2, open_check_labels: ['Mesa 4', 'Mesa 7'], unserved: 1, unserved_labels: ['Terraza 2'], prints: 3, print_usages: ['receipt'], incomplete: true },
      },
      'es',
    );
    expect(pending).toContain('- Cuentas abiertas: 2 (Mesa 4 · Mesa 7)');
    expect(pending).toContain('- Comandas sin servir: 1 (Terraza 2)');
    expect(pending).toContain('- Impresiones sin salir: 3');
    expect(pending).toContain('- No se ha podido comprobar todo lo pendiente.');
  });

  it('rectifying an invoice (INVOICE-F08): the preview first, then its words and the rectification of that invoice, then the outcome', () => {
    const question = user('E2E-RECTIFY FACT-2026-000003 rectifica la factura FACT-2026-000003 porque el precio estaba mal');
    const asked = (name: string) => ({ role: 'assistant', content: '', tool_calls: [{ function: { name } }] });
    expect(toolOf(answerTo([question]).frames)).toEqual({
      name: 'invoice__invoice__rectification_preview',
      arguments: '{"number":"FACT-2026-000003","reason":"el precio estaba mal"}',
    });
    const preview = { ...PREVIEW, original: { ...PREVIEW.original, number: 'FACT-2026-000003' } };
    const read = [question, asked('invoice__invoice__rectification_preview'), { role: 'tool', content: JSON.stringify(preview) }];
    const rectify = answerTo(read);
    // The preview is said before the card, in the same answer that asks to rectify exactly the invoice it named.
    expect(textOf(rectify.frames)).toBe(rectifyPreview(preview, 'en'));
    expect(toolOf(rectify.frames)).toEqual({
      name: 'invoice__invoice__rectify',
      arguments: '{"number":"FACT-2026-000003","reason":"el precio estaba mal"}',
    });
    expect(finish(rectify.frames)).toEqual(['tool_calls']);
    // Issued: its result names the original, now cancelled — that is the rectification done, not a refusal.
    const issued = { issued: true, invoice: { number: 'RECT-2026-000001', status: 'issued', rectifies: { number: 'FACT-2026-000003', status: 'cancelled' } } };
    const done = [...read, asked('invoice__invoice__rectify'), { role: 'tool', content: JSON.stringify(issued) }];
    expect(textOf(answerTo(done).frames)).toBe(DONE.en);
    const notConfirmed = [...read, asked('invoice__invoice__rectify'), { role: 'tool', content: '{"error": {"code": "base.assistant_not_confirmed"}}' }];
    expect(textOf(answerTo(notConfirmed).frames)).toBe(NOT_DONE.en);
    // Asked again in the same conversation (after a «Cancel»): the preview again, read now.
    const again = [...done, { role: 'assistant', content: DONE.en }, question];
    expect(toolOf(answerTo(again).frames).name).toBe('invoice__invoice__rectification_preview');
    // A preview refused (a rectifying invoice, a cancelled one, a replaced ticket): it says why, and asks for nothing.
    const why = 'Una rectificativa no se puede rectificar.';
    const refused = [question, asked('invoice__invoice__rectification_preview'), { role: 'tool', content: JSON.stringify({ error: { code: 'invoice.cannot_rectify_rectification', message: why } }) }];
    expect(toolOf(answerTo(refused).frames).name).toBe('');
    expect(textOf(answerTo(refused).frames)).toBe(`${CANNOT_RECTIFY.en} ${why}`);
  });

  it('the rectification preview as the model says it in Spanish: the original, the type, the reason, the next number, the amounts and what was left', () => {
    const whole = PREVIEW;
    expect(rectifyPreview(whole, 'es')).toBe(
      [
        'Vas a rectificar la factura **F-1** del 26/10/2026 (Talleres Pérez SL) con esta rectificativa:',
        '',
        '- Tipo: R1',
        '- Motivo: el precio estaba mal',
        '- Número: RECT-2026-000001 (el siguiente de la serie RECT; se asigna al emitirla)',
        '- Fecha: 27/10/2026',
        '- Corte × -1: -121.00 €',
        '- Base: -100.00 €',
        '- Impuestos: -21.00 €',
        '- Total: -121.00 €',
      ].join('\n'),
    );
    const left = rectifyPreview({ ...whole, invoice_type: 'R5', whole: false, original: { ...whole.original, customer_name: '', remaining: 11100 }, total_amount: -11100 }, 'es');
    expect(left).toContain('Vas a rectificar la factura **F-1** del 26/10/2026 con esta rectificativa:');
    expect(left).toContain('- Tipo: R5');
    expect(left).toContain('- Rectifica lo que queda: 111.00 € de 121.00 €');
  });

  it('reads the question from a message with attachments', () => {
    const parts = [{ type: 'text', text: 'E2E-FORMAT' }, { type: 'text', text: '[Attachment: a.md]' }];
    expect(textOf(answerTo([{ role: 'user', content: parts }]).frames)).toBe(FORMAT_ANSWER.en);
  });
});

describe('answerTo — in the language of the request (hub#1025)', () => {
  it('reads the language the Hub asks for; without one, or with one it does not speak, English (the source)', () => {
    expect(languageOf([IN.es, user('hola')])).toBe('es');
    expect(languageOf([IN.en, user('hola')])).toBe('en');
    expect(languageOf([user('hola')])).toBe('en');
    expect(languageOf([system('French'), user('bonjour')])).toBe('en');
  });

  it('each of its texts is its own in each language, never the other one’s', () => {
    for (const said of [GREETING, DONE, NOT_DONE, CANNOT_RECTIFY, NO_REASON, SLOW_ANSWER, FORMAT_ANSWER, CLAIM_ANSWER]) expect(said.en).not.toBe(said.es);
    expect(STEPS_SAID.en).not.toEqual(STEPS_SAID.es);
    // What the specs read after a write: the Spanish ones as they always did, the English ones in English.
    expect([DONE.es, NOT_DONE.es, DONE.en, NOT_DONE.en]).toEqual(['Hecho.', 'No lo he hecho.', 'Done.', 'I have not done it.']);
  });

  for (const language of LANGUAGES) {
    const asked = (...messages: Record<string, unknown>[]) => answerTo([IN[language], ...messages] as Parameters<typeof answerTo>[0]);

    it(`in ${language}: a write cancelled is not done, one that ran is done (BASE-F97)`, () => {
      const question = user('E2E-ASK online_booking__booking__cancel {"id":"1"}');
      expect(toolOf(asked(question).frames).name).toBe('online_booking__booking__cancel');
      expect(textOf(asked(question, requested('online_booking__booking__cancel'), NOT_CONFIRMED).frames)).toBe(NOT_DONE[language]);
      expect(textOf(asked(question, requested('online_booking__booking__cancel'), { role: 'tool', content: '{"id": "1"}' }).frames)).toBe(DONE[language]);
    });

    it(`in ${language}: the greeting, the format, the claim and the slow answer`, () => {
      expect(textOf(asked(user('hola')).frames)).toBe(GREETING[language]);
      expect(textOf(asked(user('E2E-FORMAT')).frames)).toBe(FORMAT_ANSWER[language]);
      expect(textOf(asked(user('E2E-CLAIM')).frames)).toBe(CLAIM_ANSWER[language]);
      expect(textOf(asked(user('E2E-SLOW')).frames)).toBe(SLOW_ANSWER[language]);
    });

    it(`in ${language}: a chain says each round, then its outcome (BASE-F101)`, () => {
      const question = user('E2E-STEPS Mesa 7');
      expect(textOf(asked(question).frames)).toBe(STEPS_SAID[language][0]);
      const read = [question, requested('demo__item__list'), { role: 'tool', content: '{"rows": []}' }];
      expect(textOf(asked(...read).frames)).toBe(STEPS_SAID[language][1]);
      expect(textOf(asked(...read, requested('demo__item__create'), NOT_CONFIRMED).frames)).toBe(NOT_DONE[language]);
    });

    it(`in ${language}: the drawer's close and the rectification are said before their card; a rectification refused says why`, () => {
      const close = user('E2E-CLOSE-CASH 25000');
      const summary = { role: 'tool', content: JSON.stringify(SUMMARY) };
      expect(textOf(asked(close, requested('cash_register__session__closing_summary'), summary).frames)).toBe(closeCashSummary(SUMMARY, language));
      const rectify = user('E2E-RECTIFY F-1 porque el precio estaba mal');
      const preview = [rectify, requested('invoice__invoice__rectification_preview'), { role: 'tool', content: JSON.stringify(PREVIEW) }];
      expect(textOf(asked(...preview).frames)).toBe(rectifyPreview(PREVIEW, language));
      expect(textOf(asked(...preview, requested('invoice__invoice__rectify'), NOT_CONFIRMED).frames)).toBe(NOT_DONE[language]);
      const why = { role: 'tool', content: JSON.stringify({ error: { code: 'invoice.cannot_rectify_rectification', message: 'No.' } }) };
      expect(textOf(asked(rectify, requested('invoice__invoice__rectification_preview'), why).frames)).toBe(`${CANNOT_RECTIFY[language]} No.`);
      // A question that gives no reason: the model writes one, in the same language.
      expect(toolOf(asked(user('E2E-RECTIFY F-1')).frames).arguments).toBe(JSON.stringify({ number: 'F-1', reason: NO_REASON[language] }));
    });
  }

  it('the close summary and the rectification preview in English: the same data, in its own words', () => {
    expect(closeCashSummary(SUMMARY, 'en')).toBe('You are about to close session **S-1**:\n\n- Counted: 250.00 €\n- Expected: 230.00 €\n- Difference: +20.00 €');
    const blind = closeCashSummary({ ...SUMMARY, expected_balance: null, difference: null, expected_hidden: true }, 'en');
    expect(blind).toBe('You are about to close session **S-1**:\n\n- Counted: 250.00 €\n- Blind count: the close compares it when you confirm.');
    const pending = closeCashSummary(
      { ...SUMMARY, pending: { open_checks: 1, open_check_labels: ['Table 4'], unserved: 1, unserved_labels: ['Terrace 2'], prints: 3, print_usages: ['receipt'], incomplete: true } },
      'en',
    );
    expect(pending).toContain('- Open checks: 1 (Table 4)');
    expect(pending).toContain('- Orders not served: 1 (Terrace 2)');
    expect(pending).toContain('- Prints not out: 3');
    expect(pending).toContain('- Not everything pending could be checked.');
    expect(rectifyPreview(PREVIEW, 'en')).toBe(
      [
        'You are about to rectify invoice **F-1** of 26/10/2026 (Talleres Pérez SL) with this rectifying invoice:',
        '',
        '- Type: R1',
        '- Reason: el precio estaba mal',
        '- Number: RECT-2026-000001 (the next one of series RECT; it is assigned when issued)',
        '- Date: 27/10/2026',
        '- Corte × -1: -121.00 €',
        '- Base: -100.00 €',
        '- Taxes: -21.00 €',
        '- Total: -121.00 €',
      ].join('\n'),
    );
    const left = rectifyPreview({ ...PREVIEW, whole: false, original: { ...PREVIEW.original, customer_name: '', remaining: 11100 } }, 'en');
    expect(left).toContain('You are about to rectify invoice **F-1** of 26/10/2026 with this rectifying invoice:');
    expect(left).toContain('- Rectifies what is left: 111.00 € of 121.00 €');
  });
});

/** One request without keep-alive (`fetch` leaves its sockets' timers armed past the test): status, type, body. */
function call(url: string, method = 'GET', body?: string): Promise<{ type: string; text: string }> {
  return new Promise((resolve, reject) => {
    const outgoing = request(url, { method, agent: false }, (response) => {
      const parts: Buffer[] = [];
      response.on('data', (part: Buffer) => parts.push(part));
      response.on('end', () => resolve({ type: String(response.headers['content-type']), text: Buffer.concat(parts).toString('utf8') }));
    });
    outgoing.on('error', reject);
    outgoing.end(body);
  });
}

describe('startProvider', () => {
  let provider: Provider;
  beforeAll(async () => {
    provider = await startProvider(0);
  });
  afterAll(() => provider.close());

  it('serves the models, a streamed answer and a dictation, and records what came', async () => {
    const models = JSON.parse((await call(`${provider.url}/models`)).text) as { data: { id: string }[] };
    expect(models.data.map((model) => model.id)).toEqual(['gpt-e2e-large', 'gpt-e2e-mini']);
    const stream = await call(`${provider.url}/chat/completions`, 'POST', JSON.stringify({ messages: [user('hola')], stream: true }));
    expect(stream.type).toBe('text/event-stream');
    expect(stream.text.trim().endsWith('data: [DONE]')).toBe(true);
    const dictated = JSON.parse((await call(`${provider.url}/audio/transcriptions`, 'POST', 'audio')).text) as { text: string };
    expect(dictated.text).toBe(DICTATION);
    expect(provider.seen.map((s) => s.path)).toEqual(['/v1/models', '/v1/chat/completions', '/v1/audio/transcriptions']);
  });
});
