import { createHmac } from 'node:crypto';
import { createServer, type IncomingHttpHeaders } from 'node:http';

import { expect, request as pwRequest, test, type Page } from '@playwright/test';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface Session { token: string; user: unknown }
interface Captured { headers: IncomingHttpHeaders; body: string }

async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  const response = await api.post(`${RUNTIME}/api/auth/pin`, { data: { name: 'Demo', pin: '0000' } });
  expect(response.ok(), `login PIN: ${response.status()} ${await response.text()}`).toBeTruthy();
  const body = await response.json();
  await api.dispose();
  return { token: body.token, user: body.user };
}

async function withSession(page: Page, session: Session): Promise<void> {
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
      localStorage.setItem('erplora.assistant.open', 'false');
      localStorage.setItem('erplora.pwa.hideInstallModal', '1');
    },
    [session.token, session.user] as const,
  );
}

test('admin crea/revoca key; webhook idempotente emite salida HMAC desde el Outbox', async ({ page }) => {
  test.setTimeout(60_000);
  const captured: Captured[] = [];
  const receiver = createServer((request, response) => {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', (chunk) => { body += chunk; });
    request.on('end', () => {
      captured.push({ headers: request.headers, body });
      response.writeHead(204).end();
    });
  });
  await new Promise<void>((resolve) => receiver.listen(0, '127.0.0.1', resolve));
  const address = receiver.address();
  if (!address || typeof address === 'string') throw new Error('receiver sin puerto TCP');

  try {
    await withSession(page, await loginByPin());
    await page.goto('/employees#apikeys');
    await expect(page).toHaveURL(/\/employees#apikeys$/);

    await page.getByRole('button', { name: 'Nueva API key' }).click();
    await page.getByTestId('api-key-name').locator('input').fill('Playwright ERP');
    await page.getByTestId('api-key-rate-limit').locator('input').fill('10');
    await page.locator('ion-checkbox[aria-label="Lectura de Catalog"]').click();
    await page.locator('ion-checkbox[aria-label="Escritura de Catalog"]').click();
    await page.getByTestId('api-key-create').click();

    const secretNode = page.getByTestId('api-key-secret');
    await expect(secretNode).toBeVisible();
    const apiKey = (await secretNode.textContent())?.trim() ?? '';
    expect(apiKey).toMatch(/^erpl_live_/);
    await page.getByRole('button', { name: 'Hecho' }).last().click();
    await expect(secretNode).toBeHidden();
    await expect(page.getByText(apiKey, { exact: true })).toHaveCount(0);

    // Gestión admin real desde el navegador: el secreto HMAC también es reveal-once.
    const subscription = await page.evaluate(async ({ port }) => {
      const session = localStorage.getItem('erplora.hub_session') ?? '';
      const response = await fetch('/api/webhooks/subscriptions', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-hub-session': session },
        body: JSON.stringify({
          name: 'Playwright receiver',
          url: `http://127.0.0.1:${port}/events`,
          events: ['catalog.item.created'],
        }),
      });
      return { status: response.status, body: await response.json() };
    }, { port: address.port });
    expect(subscription.status).toBe(200);
    const signingSecret = String(subscription.body.data.secret);
    expect(signingSecret).toMatch(/^whsec_/);

    const send = () => page.evaluate(async ({ token }) => {
      const response = await fetch('/webhook/catalog/item.create', {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: 'shop-order-2026-42', payload: { name: 'Browser Widget' } }),
      });
      return { status: response.status, body: await response.json() };
    }, { token: apiKey });

    const first = await send();
    expect(first.status).toBe(200);
    expect(first.body.replay).toBe(false);
    const replay = await send();
    expect(replay.status).toBe(200);
    expect(replay.body.replay).toBe(true);

    await expect.poll(() => captured.length, { timeout: 10_000 }).toBe(1);
    const delivery = captured[0];
    expect(delivery.headers['x-erplora-event']).toBe('catalog.item.created');
    const timestamp = String(delivery.headers['x-erplora-timestamp']);
    const deliveryId = String(delivery.headers['x-erplora-delivery']);
    const expectedSignature = `v1=${createHmac('sha256', signingSecret)
      .update(`${timestamp}.${deliveryId}.${delivery.body}`)
      .digest('hex')}`;
    expect(delivery.headers['x-erplora-signature']).toBe(expectedSignature);

    // El retry del emisor no duplicó ni la mutación ni el evento saliente.
    const items = await page.evaluate(async ({ token }) => {
      const response = await fetch('/api/v1/catalog/q/items.list', {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
        body: JSON.stringify({ params: {} }),
      });
      return { status: response.status, body: await response.json() };
    }, { token: apiKey });
    expect(items.status).toBe(200);
    expect(items.body.data.total).toBe(1);
    expect(items.body.data.rows[0].name).toBe('Browser Widget');

    // Kill switch desde la UI y verificación real contra Axum.
    await page.getByLabel('Revocar').click();
    await page.getByRole('button', { name: 'Revocar' }).last().click();
    await expect(page.getByText('Revocada', { exact: true })).toBeVisible();
    const denied = await send();
    expect(denied.status).toBe(401);
  } finally {
    await new Promise<void>((resolve, reject) => receiver.close((error) => error ? reject(error) : resolve()));
  }
});
