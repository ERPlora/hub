// Evidencia visible del loop de tool-call del asistente (hub#13).
//
// La sesión y el shell son reales. Solo se sustituyen las dos fronteras no deterministas:
// Cloud/SSE pide una query local en la primera ronda y devuelve la respuesta final en la segunda;
// el endpoint RPC de la query devuelve un total conocido. Así Playwright verifica en Chromium el
// recorrido que importa al usuario: pregunta visible → tool local → resultado reenviado → respuesta.

import { expect, request as pwRequest, test, type Page } from '@playwright/test';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface Session {
  token: string;
  user: unknown;
}

async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '0000' },
  });
  expect(res.ok(), `login PIN falló: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  await api.dispose();
  return { token: body.token, user: body.user };
}

async function withSession(page: Page, session: Session): Promise<void> {
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
      localStorage.setItem('erplora.pwa.hideInstallModal', '1');
      sessionStorage.removeItem('erplora.assistant.history');
    },
    [session.token, session.user] as const,
  );
}

test('el asistente ejecuta una tool local y muestra la respuesta final', async ({ page }) => {
  const session = await loginByPin();
  await withSession(page, session);

  let assistantRound = 0;
  const assistantBodies: Array<{ messages: Array<Record<string, unknown>> }> = [];
  await page.route('**/api/assistant/chat/stream', async (route) => {
    assistantRound += 1;
    assistantBodies.push(route.request().postDataJSON());
    const body = assistantRound === 1
      ? [
          'data: {"type":"function_call","name":"sales.summary","call_id":"call-1","arguments":"{\\"period\\":\\"today\\"}","kind":"query"}',
          'data: {"type":"done"}',
        ].join('\n\n') + '\n\n'
      : [
          'data: {"type":"token","text":"Hoy llevas 12 ventas."}',
          'data: {"type":"done"}',
        ].join('\n\n') + '\n\n';
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body });
  });

  let localToolBody: Record<string, unknown> | undefined;
  await page.route('**/api/query', async (route) => {
    localToolBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, data: { total: 12 } }),
    });
  });

  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Asistente' }).click();
  await expect(page.getByRole('dialog', { name: 'Asistente' })).toBeVisible();

  const input = page.getByPlaceholder('Escribe un mensaje…');
  await input.fill('¿Cuántas ventas llevo hoy?');
  await page.getByRole('button', { name: 'Enviar' }).click();

  await expect(page.getByText('Hoy llevas 12 ventas.')).toBeVisible();
  expect(localToolBody).toEqual({ name: 'sales.summary', params: { period: 'today' } });
  expect(assistantBodies).toHaveLength(2);
  const continuedMessages = assistantBodies[1].messages;
  expect(continuedMessages).toEqual(expect.arrayContaining([
    expect.objectContaining({ role: 'assistant', tool_calls: expect.any(Array) }),
    expect.objectContaining({ role: 'tool', tool_call_id: 'call-1', content: '{"total":12}' }),
  ]));
});
