// @vitest-environment node
// The assistant's e2e provider (assistant-provider.ts): it answers as OpenAI streams — text in pieces, a tool call in
// fragments with `finish_reason: tool_calls`, then the usage —, by the marker of the question, and tells the outcome
// of a tool once its result comes back.
import { request } from 'node:http';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { answerTo, CLAIM_ANSWER, closeCashSummary, DICTATION, FORMAT_ANSWER, GREETING, type Provider, startProvider } from './assistant-provider';

type Frame = { choices: { delta: { content?: string; tool_calls?: { function: { name?: string; arguments?: string } }[] }; finish_reason: string | null }[] };

const textOf = (frames: unknown[]) =>
  (frames as Frame[]).flatMap((frame) => frame.choices.map((choice) => choice.delta.content ?? '')).join('');
const finish = (frames: unknown[]) => (frames as Frame[]).flatMap((frame) => frame.choices.map((c) => c.finish_reason)).filter(Boolean);
const toolOf = (frames: unknown[]) => {
  const pieces = (frames as Frame[]).flatMap((frame) => frame.choices.flatMap((c) => c.delta.tool_calls ?? []));
  return { name: pieces.map((p) => p.function.name ?? '').join(''), arguments: pieces.map((p) => p.function.arguments ?? '').join('') };
};
const user = (content: string) => ({ role: 'user', content });

describe('answerTo', () => {
  it('a question without a marker: the greeting, streamed in pieces, ending in «stop»', () => {
    const answer = answerTo([user('hola')]);
    expect(textOf(answer.frames)).toBe(GREETING);
    expect(answer.frames.length).toBeGreaterThan(3);
    expect(finish(answer.frames)).toEqual(['stop']);
  });

  it('the format, the claim and a slow answer by their markers', () => {
    expect(textOf(answerTo([user('E2E-FORMAT')]).frames)).toBe(FORMAT_ANSWER);
    expect(textOf(answerTo([user('E2E-CLAIM')]).frames)).toBe(CLAIM_ANSWER);
    expect(answerTo([user('E2E-SLOW')]).delayMs).toBeGreaterThan(0);
    expect(answerTo([user('E2E-DOWN')]).status).toBe(500);
  });

  it('a write: the tool call in fragments; then, with its result, the outcome', () => {
    const asked = answerTo([user('E2E-CREATE Mesa 4')]);
    expect(toolOf(asked.frames)).toEqual({ name: 'demo__item__create', arguments: '{"name":"Mesa 4"}' });
    expect(finish(asked.frames)).toEqual(['tool_calls']);
    expect(toolOf(answerTo([user('E2E-DELETE abc')]).frames)).toEqual({ name: 'demo__item__delete', arguments: '{"id":"abc"}' });
    expect(textOf(answerTo([user('x'), { role: 'tool', content: '{"id": "1"}' }]).frames)).toBe('Hecho.');
    expect(textOf(answerTo([user('x'), { role: 'tool', content: '{"error": {"code": "base.assistant_not_confirmed"}}' }]).frames)).toBe('No lo he hecho.');
  });

  it('a chain: first a read, then a write, then the outcome (BASE-G119)', () => {
    const question = user('E2E-CHAIN Mesa 7');
    const asked = (name: string) => ({ role: 'assistant', content: '', tool_calls: [{ function: { name } }] });
    expect(toolOf(answerTo([question]).frames)).toEqual({ name: 'demo__item__list', arguments: '{}' });
    const read = [question, asked('demo__item__list'), { role: 'tool', content: '{"rows": []}' }];
    expect(toolOf(answerTo(read).frames)).toEqual({ name: 'demo__item__create', arguments: '{"name":"Mesa 7"}' });
    const written = [...read, asked('demo__item__create'), { role: 'tool', content: '{"id": "1"}' }];
    expect(textOf(answerTo(written).frames)).toBe('Hecho.');
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
      counted: 25000,
      expected_balance: 23000,
      difference: 2000,
      expected_hidden: false,
      review: { open_checks: 2, open_check_labels: ['Mesa 4', 'Mesa 7'], unserved: 0, unserved_labels: [], prints: 0, print_usages: [], incomplete: false },
    };
    const read = [question, asked('cash_register__session__closing_summary'), { role: 'tool', content: JSON.stringify(summary) }];
    const close = answerTo(read);
    // The summary is said before the card, in the same answer that asks for the close of exactly that session.
    expect(textOf(close.frames)).toBe(closeCashSummary(summary));
    expect(toolOf(close.frames)).toEqual({
      name: 'cash_register__session__close',
      arguments: '{"session":"S-261024-0001","closing_balance":25000}',
    });
    expect(finish(close.frames)).toEqual(['tool_calls']);
    const closed = [...read, asked('cash_register__session__close'), { role: 'tool', content: '{"status": "closed"}' }];
    expect(textOf(answerTo(closed).frames)).toBe('Hecho.');
    // A summary refused (the count required and not said, no open session): it is said, and nothing is asked for.
    const refused = [question, asked('cash_register__session__closing_summary'), { role: 'tool', content: '{"error": {"code": "cash_register.no_open_session"}}' }];
    expect(toolOf(answerTo(refused).frames).name).toBe('');
    expect(textOf(answerTo(refused).frames)).toBe('No lo he hecho.');
  });

  it('the close summary as the model says it: the expected and the difference only when they came, and what is pending', () => {
    const base = { number: 'S-1', counted: 25000, review: { open_checks: 0, open_check_labels: [], unserved: 0, unserved_labels: [], prints: 0, print_usages: [], incomplete: false } };
    expect(closeCashSummary({ ...base, expected_balance: 23000, difference: 2000, expected_hidden: false })).toBe(
      'Vas a cerrar la sesión **S-1**:\n\n- Contado: 250.00 €\n- Esperado: 230.00 €\n- Diferencia: +20.00 €',
    );
    expect(closeCashSummary({ ...base, expected_balance: 23000, difference: -500, expected_hidden: false })).toContain('- Diferencia: -5.00 €');
    const blind = closeCashSummary({ ...base, expected_balance: null, difference: null, expected_hidden: true });
    expect(blind).toBe('Vas a cerrar la sesión **S-1**:\n\n- Contado: 250.00 €\n- Arqueo ciego: el cierre lo comparará al confirmar.');
    const pending = closeCashSummary({
      ...base,
      expected_balance: null,
      difference: null,
      expected_hidden: true,
      review: { open_checks: 2, open_check_labels: ['Mesa 4', 'Mesa 7'], unserved: 1, unserved_labels: ['Terraza 2'], prints: 3, print_usages: ['receipt'], incomplete: true },
    });
    expect(pending).toContain('- Cuentas abiertas: 2 (Mesa 4 · Mesa 7)');
    expect(pending).toContain('- Comandas sin servir: 1 (Terraza 2)');
    expect(pending).toContain('- Impresiones sin salir: 3');
    expect(pending).toContain('- No se ha podido comprobar todo lo pendiente.');
  });

  it('reads the question from a message with attachments', () => {
    const parts = [{ type: 'text', text: 'E2E-FORMAT' }, { type: 'text', text: '[Attachment: a.md]' }];
    expect(textOf(answerTo([{ role: 'user', content: parts }]).frames)).toBe(FORMAT_ANSWER);
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
