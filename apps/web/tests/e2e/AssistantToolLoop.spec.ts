// Browser → Vite → Axum → runtime/DB is entirely real. The only deterministic boundary is the
// Cloud assistant/embeddings service started by playwright.assistant.config.ts.

import { expect, request as pwRequest, test, type Page, type Request } from '@playwright/test';
import { resolve } from 'node:path';

const RUNTIME = `http://127.0.0.1:${process.env.ASSISTANT_E2E_RUNTIME_PORT ?? '8787'}`;
const CLOUD = `http://127.0.0.1:${process.env.ASSISTANT_E2E_CLOUD_PORT ?? '18991'}`;
const HUB_ID = 'assistant-e2e-hub';
const FIXTURE = resolve(process.cwd(), '../../crates/server/tests/fixture_assistant');

interface Session { token: string; user: unknown }

test.afterAll(async () => {
  await fetch(`${CLOUD}/__shutdown`, { method: 'POST' }).catch(() => undefined);
});

async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  const response = await api.post(`${RUNTIME}/api/auth/pin`, { data: { name: 'Demo', pin: '0000' } });
  expect(response.ok(), `login PIN falló: ${response.status()} ${await response.text()}`).toBeTruthy();
  const body = await response.json();
  await api.dispose();
  return { token: body.token, user: body.user };
}

async function moduleAction(session: Session, path: string, data?: unknown) {
  const api = await pwRequest.newContext({
    extraHTTPHeaders: { 'X-Hub-Session': session.token, 'X-Hub-Id': HUB_ID },
  });
  const response = await api.post(`${RUNTIME}${path}`, data === undefined ? {} : { data });
  const text = await response.text();
  await api.dispose();
  return { ok: response.ok(), status: response.status(), text };
}

async function withSession(page: Page, session: Session): Promise<void> {
  await page.addInitScript(([token, user]) => {
    localStorage.setItem('erplora.hub_session', token as string);
    localStorage.setItem('erplora.session', JSON.stringify(user));
    localStorage.setItem('erplora.pwa.hideInstallModal', '1');
    sessionStorage.removeItem('erplora.assistant.history');
  }, [session.token, session.user] as const);
}

async function observations() {
  return fetch(`${CLOUD}/__observations`).then((response) => response.json()) as Promise<{
    embeddings: Array<{ body: { texts: string[] }; headers: { hubId: string; hubToken: string } }>;
    assistant: Array<{ body: { tools: Array<{ name: string; kind: string }> }; headers: { hubId: string; hubToken: string } }>;
  }>;
}

async function indexedRows() {
  const response = await fetch(`${CLOUD}/__index`);
  const text = await response.text();
  expect(response.ok, `inspección knowledge_chunk falló: ${text}`).toBeTruthy();
  return (JSON.parse(text) as {
    rows: Array<{ refId: string; source: string; version: string }>;
  }).rows;
}

function rpcCapture(request: Request) {
  const path = new URL(request.url()).pathname;
  if (request.method() !== 'POST' || !['/api/query', '/api/command'].includes(path)) return null;
  return { path, body: request.postDataJSON(), headers: request.headers() };
}

test('tool routing + install/reindex/uninstall con query y command reales', async ({ page }) => {
  const session = await loginByPin();
  await moduleAction(session, '/api/modules/assistant_fixture/uninstall'); // idempotencia si se usa BD externa
  await fetch(`${CLOUD}/__reset`, { method: 'POST' });

  const installed = await moduleAction(session, '/api/modules/install', { dir: FIXTURE });
  expect(installed.ok, `install falló (${installed.status}): ${installed.text}`).toBeTruthy();
  await expect.poll(async () => (await observations()).embeddings.length).toBeGreaterThan(0);
  const firstIndex = await indexedRows();
  expect(firstIndex).toHaveLength(3); // agent + query + command, persistidos en PostgreSQL real
  expect(firstIndex.every((row) => row.refId === 'assistant_fixture')).toBe(true);

  // Reinstalar ejerce el camino real de reindex: los ids estables se reemplazan, no se duplican.
  const embeddingCallsBeforeReindex = (await observations()).embeddings.length;
  const reinstalled = await moduleAction(session, '/api/modules/install', { dir: FIXTURE });
  expect(reinstalled.ok, `reinstall falló (${reinstalled.status}): ${reinstalled.text}`).toBeTruthy();
  await expect.poll(async () => (await observations()).embeddings.length).toBeGreaterThan(embeddingCallsBeforeReindex);
  expect(await indexedRows()).toEqual(firstIndex);

  const rpc: NonNullable<ReturnType<typeof rpcCapture>>[] = [];
  const assistantHeaders: Array<Record<string, string>> = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/assistant/chat/stream') {
      assistantHeaders.push(request.headers());
    }
    const captured = rpcCapture(request);
    if (captured) rpc.push(captured);
  });
  await withSession(page, session);
  await page.goto('/dashboard');
  await page.getByRole('button', { name: /Asistente|Assistant/ }).click();
  const input = page.getByPlaceholder(/Escribe un mensaje|Type a message/);
  const send = page.getByRole('button', { name: /Enviar|Send/ });

  const marker = `pw-${Date.now()}`;
  await input.fill(`CREATE ${marker}`);
  await send.click();
  // El Cloud mintió con kind=query. Axum lo sustituye por command y el navegador exige confirmar.
  await expect(page.getByText(/Confirmar acción del asistente|Confirm assistant action/)).toBeVisible();
  await page.getByRole('button', { name: /Ejecutar|Run/ }).click();
  await expect(page.getByText('Marcador creado por el runtime real.')).toBeVisible();

  await input.fill(`FIND ${marker}`);
  await send.click();
  // El Cloud mintió con kind=command. El catálogo lo corrige a query: no aparece confirmación.
  await expect(page.getByText('Marcador encontrado por el runtime real.')).toBeVisible();

  expect(rpc.map((call) => call.path)).toEqual(expect.arrayContaining(['/api/command', '/api/query']));
  const command = rpc.find((call) => call.body?.name === 'assistant_fixture.item.create');
  const query = rpc.find((call) => call.body?.name === 'assistant_fixture.items.find');
  expect(command?.body).toEqual({ name: 'assistant_fixture.item.create', payload: { name: marker } });
  expect(query?.body).toEqual({ name: 'assistant_fixture.items.find', params: { name: marker } });
  expect(command?.headers['x-hub-session']).toBe(session.token);
  expect(query?.headers['x-hub-session']).toBe(session.token);
  expect(assistantHeaders.length).toBeGreaterThanOrEqual(4);
  expect(assistantHeaders.every((headers) => headers['x-hub-session'] === session.token)).toBe(true);

  const beforeUninstall = await observations();
  expect(beforeUninstall.embeddings[0].headers).toEqual({ hubId: HUB_ID, hubToken: 'assistant-e2e-token' });
  expect(beforeUninstall.assistant.length).toBeGreaterThanOrEqual(4); // call + tool result, twice
  for (const call of beforeUninstall.assistant) {
    expect(call.headers).toEqual({ hubId: HUB_ID, hubToken: 'assistant-e2e-token' });
    expect(call.body.tools.map((tool) => tool.name).sort()).toEqual([
      'assistant_fixture.item.create',
      'assistant_fixture.items.find',
    ]);
  }

  const removed = await moduleAction(session, '/api/modules/assistant_fixture/uninstall');
  expect(removed.ok, `uninstall falló (${removed.status}): ${removed.text}`).toBeTruthy();
  await expect.poll(async () => (await indexedRows()).length).toBe(0);
  await fetch(`${CLOUD}/__reset`, { method: 'POST' });
  await input.fill('NO TOOLS');
  await send.click();
  await expect(page.getByText('Sin herramientas activas.')).toBeVisible();
  const afterUninstall = await observations();
  expect(afterUninstall.assistant.at(-1)?.body.tools).toEqual([]);
});
