// ADR-0177 / hub#224 — navegador real → Vite → Axum → Runtime/Postgres → mini-Cloud media.
// Este archivo no intercepta rutas: todas las respuestas proceden de los handlers de producción.

import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('erplora.hub_session', 'pw-session');
    localStorage.setItem('erplora.pwa.hideInstallModal', '1');
    localStorage.setItem(
      'erplora.session',
      JSON.stringify({
        id: 'owner', name: 'Owner', email: 'owner@example.test', role: 'owner', permissions: ['*'],
      }),
    );
  });
});

test('autoría, media y toggle usan el Axum real sin interceptores', async ({ page, request }) => {
  const publicUrl = process.env.HUB_PUBLIC_URL;
  test.skip(!publicUrl, 'requiere public_e2e_server');

  await page.goto('/settings#hub');
  await expect(page.getByTestId('public-presence-restart-note')).toContainText('Reinicia el Hub');

  await page.getByTestId('public-page-open').click();
  const modal = page.getByTestId('public-page-modal');
  await expect(modal).toBeVisible();
  await expect(modal.getByTestId('page-editor')).toBeVisible();
  await expect(modal.getByText('Nuestra carta')).toBeVisible();

  const saveResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/public-pages/menu')
      && response.request().method() === 'PUT');
  await modal.getByTestId('public-page-save').click();
  expect((await saveResponse).status()).toBe(200);

  const uploadedUrl = await page.evaluate(async () => {
    const png = Uint8Array.from(
      atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='),
      (char) => char.charCodeAt(0),
    );
    const form = new FormData();
    form.append('folder', 'pages/menu');
    form.append('files', new File([png], 'plato.png', { type: 'image/png' }));
    const response = await fetch('/api/media/upload', { method: 'POST', body: form });
    const body = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(body));
    return body.data.file.url as string;
  });
  expect(uploadedUrl).toBe('/files/pages/menu/plato.png');

  const rejectedActiveContent = await page.evaluate(async () => {
    const form = new FormData();
    form.append('folder', 'pages/menu');
    form.append('files', new File(['<svg onload="alert(1)"/>'], 'x.svg', { type: 'image/svg+xml' }));
    return (await fetch('/api/media/upload', { method: 'POST', body: form })).status;
  });
  expect(rejectedActiveContent).toBe(415);

  const putStatus = await page.evaluate(async (imageUrl) => {
    const response = await fetch('/api/public-pages/menu', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        blocks: [
          { type: 'header', data: { text: 'Carta E2E', level: 1 } },
          { type: 'paragraph', data: { text: 'Contenido guardado en Postgres' } },
          { type: 'image', data: { file: { url: imageUrl }, caption: 'Plato del día' } },
        ],
      }),
    });
    return response.status;
  }, uploadedUrl);
  expect(putStatus).toBe(200);

  await modal.getByTestId('public-page-close').click();
  const toggle = page.getByTestId('public-presence-toggle');
  await expect(toggle).toHaveAttribute('aria-checked', 'true');
  const settingResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/settings') && response.request().method() === 'PUT');
  await toggle.click();
  expect((await settingResponse).status()).toBe(200);

  const effective = await page.evaluate(async () => {
    const [settings, context] = await Promise.all([
      fetch('/api/settings').then((response) => response.json()),
      fetch('/api/hub/context').then((response) => response.json()),
    ]);
    return {
      desired: settings['public.landing.visible'],
      active: context.public_landing_visible,
    };
  });
  expect(effective).toEqual({ desired: false, active: true });

  const publicPage = await page.goto(`${publicUrl}/p/menu`);
  expect(publicPage?.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Carta E2E' })).toBeVisible();
  await expect(page.getByText('Contenido guardado en Postgres')).toBeVisible();
  await expect(page.getByText('Cafe con leche')).toBeVisible();
  const image = page.getByRole('img', { name: 'Plato del día' });
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBe(1);

  // Restaura el fixture para que este caso y el de SSR puedan ejecutarse solos o en cualquier orden.
  await request.put(`${publicUrl}/api/public-pages/menu`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      blocks: [
        { type: 'header', data: { text: 'Nuestra carta', level: 1 } },
        { type: 'paragraph', data: { text: 'Café <b>recién molido</b>' } },
      ],
    },
  });
  await request.put(`${publicUrl}/api/settings`, {
    headers: { 'Content-Type': 'application/json' },
    data: { 'public.landing.visible': true },
  });
});

test('SSR, CSP, ETag, Host y SEO proceden del listener Axum real', async ({ page, request }) => {
  const publicUrl = process.env.HUB_PUBLIC_URL;
  test.skip(!publicUrl, 'requiere public_e2e_server');

  const landing = await page.goto(`${publicUrl}/`);
  expect(landing?.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Bar Pepe' })).toBeVisible();
  await expect(page.getByText('Calle Mayor 1')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Menu' })).toHaveAttribute('href', '/p/menu');
  expect(await page.locator('script').count()).toBe(0);
  expect(landing?.headers()['content-security-policy']).toContain("script-src 'none'");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', `${publicUrl}/`);

  const publicPage = await page.goto(`${publicUrl}/p/menu`);
  expect(publicPage?.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Nuestra carta' })).toBeVisible();
  await expect(page.getByText('Café recién molido')).toBeVisible();
  await expect(page.getByText('Cafe con leche')).toBeVisible();
  expect(await page.locator('script').count()).toBe(0);
  expect(publicPage?.headers()['content-security-policy']).toContain("script-src 'none'");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', `${publicUrl}/p/menu`);

  const etag = publicPage?.headers().etag;
  expect(etag).toBeTruthy();
  const conditional = await request.get(`${publicUrl}/p/menu`, {
    headers: { 'If-None-Match': etag as string },
  });
  expect(conditional.status()).toBe(304);

  const robots = await request.get(`${publicUrl}/robots.txt`);
  expect(await robots.text()).toContain(`${publicUrl}/sitemap.xml`);
  const sitemap = await request.get(`${publicUrl}/sitemap.xml`);
  expect(await sitemap.text()).toContain(`${publicUrl}/p/menu`);

  const origin = new URL(publicUrl as string);
  const wrongHost = await request.get(`${publicUrl}/p/menu`, {
    headers: { Host: `wrong.${origin.hostname}` },
  });
  expect(wrongHost.status()).toBe(421);
});
