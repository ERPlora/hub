// @vitest-environment node
// The simulated owner of a scenario: a fixed model, the same for every assistant under test, plays the business owner
// from its persona and facts only, and says when the job looks done or it gives up. Its tokens and cost are its own.
import { describe, expect, it } from 'vitest';

import { askOwner, type Exchange, OWNER_DEFAULT, ownerChoice, ownerRequest, ownerSystem, parseOwnerReply } from './assistant-owner';
import type { Scenario } from './assistant-scenario';

const scenario = {
  language: 'es',
  owner: {
    persona: 'Marta, dueña del bar La Esquina',
    goal: 'Añadir la tarta de zanahoria a la carta',
    upFront: ['Se vende a 5,50 €'],
    ifAsked: ['Va en Postres'],
  },
} as unknown as Scenario;

const transcript: Exchange[] = [
  { who: 'owner', text: 'Añade la tarta de zanahoria a 5,50' },
  { who: 'assistant', text: '¿En qué categoría la pongo?', cards: [] },
];

describe('ownerChoice', () => {
  it('is Sonnet through OpenRouter unless QA_OWNER_MODEL names another, with the key read from its variable', () => {
    expect(ownerChoice({ QA_OPENROUTER_API_KEY: 'k' })).toEqual({ model: OWNER_DEFAULT, baseUrl: 'https://openrouter.ai/api/v1', keyEnv: 'QA_OPENROUTER_API_KEY' });
    expect(OWNER_DEFAULT).toBe('anthropic/claude-sonnet-5.5');
    expect(ownerChoice({ QA_OPENROUTER_API_KEY: 'k', QA_OWNER_MODEL: 'openai/gpt-5.5' }).model).toBe('openai/gpt-5.5');
  });

  it('stops a run without the key, saying which variable to export', () => {
    expect(() => ownerChoice({})).toThrow(/QA_OPENROUTER_API_KEY/);
  });
});

describe('ownerSystem', () => {
  it('gives the owner only its persona, goal and facts, split by when it says them, in its language', () => {
    const text = ownerSystem(scenario);
    expect(text).toContain('Marta, dueña del bar La Esquina');
    expect(text).toContain('Añadir la tarta de zanahoria a la carta');
    expect(text).toMatch(/up front[\s\S]*Se vende a 5,50 €[\s\S]*only if[\s\S]*Va en Postres/);
    expect(text).toContain('Spanish');
    expect(text).toContain('[DONE]');
    expect(text).toContain('[GIVE UP]');
    expect(text).toMatch(/never mention tools/i);
  });

  it('says there is nothing more to tell when the owner keeps no fact back', () => {
    const text = ownerSystem({ ...scenario, owner: { ...scenario.owner, ifAsked: [] }, language: 'en' } as Scenario);
    expect(text).toMatch(/only if the assistant asks you about it:\n- \(nothing\)/);
    expect(text).toContain('Write only in English');
  });
});

describe('ownerRequest', () => {
  it('asks the owner model with the least randomness, the whole conversation as it saw it, and its usage counted', () => {
    const request = ownerRequest(ownerChoice({ QA_OPENROUTER_API_KEY: 'k' }), scenario, [
      ...transcript.slice(0, 1),
      { who: 'assistant', text: 'Hecho.', cards: ['Crear producto: Tarta de zanahoria'] },
    ]);
    expect(request.url).toBe('https://openrouter.ai/api/v1/chat/completions');
    expect(request.body.temperature).toBe(0);
    expect(request.body.model).toBe(OWNER_DEFAULT);
    expect(request.body.usage).toEqual({ include: true });
    expect(request.body.messages[0]).toEqual({ role: 'system', content: ownerSystem(scenario) });
    const asked = request.body.messages[1].content;
    expect(asked).toContain('YOU: Añade la tarta de zanahoria a 5,50');
    expect(asked).toContain('ASSISTANT: Hecho.');
    expect(asked).toContain('[On the screen you confirmed: Crear producto: Tarta de zanahoria]');
  });
});

describe('parseOwnerReply', () => {
  const answer = (content: string, usage: Record<string, number> = { prompt_tokens: 120, completion_tokens: 9, cost: 0.0004 }) => ({ choices: [{ message: { content } }], usage });

  it('reads what the owner says next, with its tokens and cost', () => {
    expect(parseOwnerReply(answer('En Postres, claro.'))).toEqual({ say: 'En Postres, claro.', end: null, tokensIn: 120, tokensOut: 9, costUsd: 0.0004 });
  });

  it('reads the end of the conversation: the job looks done, or the owner gives up', () => {
    expect(parseOwnerReply(answer('[DONE]')).end).toBe('done');
    expect(parseOwnerReply(answer('Vale, gracias. [DONE]'))).toMatchObject({ say: null, end: 'done' });
    expect(parseOwnerReply(answer('[GIVE UP]')).end).toBe('gave_up');
  });

  it('keeps an unknown cost unknown, never zero, and refuses an empty answer', () => {
    expect(parseOwnerReply(answer('Sí', { prompt_tokens: 1, completion_tokens: 1 })).costUsd).toBeNull();
    expect(() => parseOwnerReply(answer('  '))).toThrow(/said nothing/);
    expect(() => parseOwnerReply({ error: { message: 'no credits' } })).toThrow(/no credits/);
  });
});

describe('askOwner', () => {
  it('posts the request with the key and reads the reply', async () => {
    const seen: { url: string; init: RequestInit }[] = [];
    const fetcher = async (url: string, init: RequestInit) => {
      seen.push({ url, init });
      return new Response(JSON.stringify({ choices: [{ message: { content: 'En Postres' } }], usage: { prompt_tokens: 5, completion_tokens: 2, cost: 0.001 } }));
    };
    const reply = await askOwner({ fetcher, choice: ownerChoice({ QA_OPENROUTER_API_KEY: 'k' }), key: 'secret' }, scenario, transcript);
    expect(reply.say).toBe('En Postres');
    expect(seen[0].url).toBe('https://openrouter.ai/api/v1/chat/completions');
    expect((seen[0].init.headers as Record<string, string>).Authorization).toBe('Bearer secret');
  });

  it('fails with the status and what the API said, never with the key', async () => {
    const fetcher = async () => new Response('{"error":{"message":"model not found"}}', { status: 404 });
    await expect(askOwner({ fetcher, choice: ownerChoice({ QA_OPENROUTER_API_KEY: 'k' }), key: 'secret' }, scenario, transcript)).rejects.toThrow(/404.*model not found/);
  });
});
