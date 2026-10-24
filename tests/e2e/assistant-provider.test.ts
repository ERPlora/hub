// @vitest-environment node
// The assistant's e2e provider (assistant-provider.ts): it answers as OpenAI streams — text in pieces, a tool call in
// fragments with `finish_reason: tool_calls`, then the usage —, by the marker of the question, and tells the outcome
// of a tool once its result comes back.
import { request } from 'node:http';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { answerTo, CLAIM_ANSWER, DICTATION, FORMAT_ANSWER, GREETING, type Provider, startProvider } from './assistant-provider';

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
