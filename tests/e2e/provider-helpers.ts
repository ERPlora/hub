// What the e2e that reach the assistant through the e2e's provider share (assistant-provider.ts, an OpenAI-compatible
// server this process starts; the stack's SaaS seeded with it, README «El asistente»): the provider started and checked
// against the SaaS, the worker's relay played one tick at a time from a process of its own, and what the assistant was
// asked.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { expect, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { saasSql } from './assistant-real';
import { parkedEvent, RELAY, runNowAsksTheAssistant } from './flow-helpers';
import { HUB_DIR, psql } from './helpers';
import { STACK } from './stack';

const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);

/** The e2e's provider, started once the stack's SaaS is known to send the assistant's turns to it. */
export async function seededProvider(): Promise<Provider> {
  const provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${STACK.saasDatabase} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  return provider;
}

/** Registers the hooks of a spec that asks the assistant: the provider started before its tests and closed after them,
 *  with the spec's `cleanUp` once on each side. Gives the provider once they have run. */
export function providerSpec(cleanUp: () => void): () => Provider {
  let provider: Provider;
  test.beforeAll(async () => {
    provider = await seededProvider();
    cleanUp();
  });
  test.afterAll(async () => {
    cleanUp();
    await provider?.close();
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

/** The worker's part of an «Ask the assistant» step (FLOW-F38): the newest `flow.run.parked` of the automation `flowId`
 *  relayed, so the assistant is asked after that COMMIT. */
export const workerAsks = (flowId: string): Promise<void> => relay(parkedEvent(flowId));

/** «Run now» from the editor of the automation `flowId`, and the worker's part of its step: what the assistant wants
 *  waits in «Waiting for your answer». */
export async function runAndAsk(page: Page, flowId: string): Promise<void> {
  await runNowAsksTheAssistant(page);
  await workerAsks(flowId);
  await expect.poll(() => psql(`select count(*) from flow_question where flow_id = '${flowId}' and status = 'pending'`)).toBe('1');
}

/** After the owner's answer, the step goes back to the assistant with what happened, and the run of `flowId` finishes. */
export async function runFinishes(flowId: string): Promise<void> {
  await workerAsks(flowId);
  await expect.poll(() => psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');
}

/** The turns the assistant was asked so far, the last one last. */
export const chats = (provider: Provider): Provider['seen'] => provider.seen.filter((seen) => seen.path === '/v1/chat/completions');

/** The worker's part of the parked run of the automation `flowId`, which asks the assistant exactly once: that turn. */
export async function askedOnce(provider: Provider, flowId: string): Promise<Provider['seen'][number]> {
  const before = chats(provider).length;
  await workerAsks(flowId);
  const turns = chats(provider).slice(before);
  expect(turns).toHaveLength(1);
  return turns[0];
}

type Tool = { function: { name: string; parameters?: { properties?: Record<string, unknown> } } };

/** The inputs the assistant was offered for `name` in a turn's request. */
export function inputsOf(body: unknown, name: string): string[] {
  const tool = ((body as { tools?: Tool[] }).tools ?? []).find((offered) => offered.function.name === name);
  expect(tool, `${name} offered`).toBeTruthy();
  return Object.keys(tool!.function.parameters?.properties ?? {});
}
