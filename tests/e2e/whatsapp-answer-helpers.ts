// What the e2e of WhatsApp's automatic answers shares (WHATSAPP_INBOX-F14, F15): the real dependencies of an answer that
// asks the assistant, around each spec's own cleaning. The Hub of the stack, its SaaS's gateway and, behind it, the e2e's
// provider (assistant-provider.ts, started here; the SaaS seeded with it, README «El asistente»), with the channel
// connected before each test and `a`'s photo as it found it after them; and the worker's relay, which this stack does not
// run, played one tick at a time from a process of its own.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { expect, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { saasSql } from './assistant-real';
import { RELAY } from './flow-helpers';
import { HUB_DIR, psql } from './helpers';
import { STACK } from './stack';
import { keepPhoto, pushChannel, receive, restorePhoto } from './whatsapp-helpers';

const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);

/** Registers the hooks of a spec of an answer that asks the assistant, and gives its provider once they have run. */
export function answerSpec(cleanUp: () => void): () => Provider {
  let provider: Provider;
  test.beforeAll(async () => {
    keepPhoto();
    provider = await startProvider(PROVIDER_PORT);
    const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
    expect(seeded, `the SaaS ${STACK.saasDatabase} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  });
  test.beforeEach(() => {
    cleanUp();
    pushChannel({ status: 'connected' });
  });
  test.afterAll(async () => {
    cleanUp();
    await provider?.close();
    restorePhoto();
  });
  return () => provider;
}

/** One tick of the worker's relay (in `a`'s database: the e2e stack's worker relays nothing): the outbox event `id` handed
 *  to Automations' reaction, and what it leaves for after its COMMIT made at once. It does not block this process: the
 *  provider the SaaS asks lives here, and must answer. */
export async function relay(id: string): Promise<void> {
  await promisify(execFile)('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', RELAY], {
    cwd: HUB_DIR,
    env: { ...process.env, FLOW_EVENT: id },
  });
}

/** The turns the assistant was asked so far. */
export const chats = (provider: Provider): number => provider.seen.filter((seen) => seen.path === '/v1/chat/completions').length;

/** The customer writes `text` from `phone`, as erplora.com pushes it, and the relay hands it to the answer; her message. */
export async function customerWrites(phone: string, text: string, name: string): Promise<ReturnType<typeof receive>> {
  const message = receive(phone, text, name);
  const received = psql(`select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${message.id}'`);
  expect(received, 'whatsapp_inbox.message.received of the message in the outbox').not.toBe('');
  await relay(received);
  return message;
}
