// Ejecuta las aserciones de `FirstRunPage.spec.ts` con el paquete `playwright` GLOBAL, porque el
// runner `@playwright/test` no se puede instalar aquí (el registry npm falla la verificación de
// certificado tras el proxy de inspección corporativo, y desactivar strict-ssl no es cosa mía).
// Mismo contrato, mismo runtime real, cero mocks. Cuando `@playwright/test` esté disponible,
// el .spec.ts es la versión buena y esto se borra.
//
//   node tests/e2e/run-first-run-check.mjs
//
// Requiere el runtime en :8787 con `HUB_MODULES_DIR` vacío y BD fresca, y Vite en :5173.

import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const globalRoot = execSync('npm root -g').toString().trim();
const { chromium } = require(`${globalRoot}/playwright`);

const WEB = process.env.HUB_WEB_URL ?? 'http://localhost:5173';
const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const REAL_MODULE_DIR = process.env.HUB_TEST_MODULE_DIR ?? '';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail });
  console.log(`${ok ? '  ✓' : '  ✗'} ${name}${detail && !ok ? ` — ${detail}` : ''}`);
};

async function loginByPin() {
  const res = await fetch(`${RUNTIME}/api/auth/pin`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name: 'Demo', pin: '0000' }),
  });
  if (!res.ok) throw new Error(`login PIN: ${res.status} ${await res.text()}`);
  const body = await res.json();
  if (!body.token) throw new Error('el runtime no devolvió token de sesión');
  return { token: body.token, user: body.user };
}

async function newPage(browser, session) {
  const ctx = await browser.newContext();
  await ctx.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user],
  );
  return ctx.newPage();
}

const browser = await chromium.launch();
try {
  const session = await loginByPin();
  console.log('\nprimer arranque de un hub vacío');

  // 1) sin módulos instalados, el shell desvía a la pantalla de puesta en marcha
  {
    const page = await newPage(browser, session);
    await page.goto(WEB + '/');
    await page.waitForURL(/\/first-run$/, { timeout: 10_000 }).catch(() => {});
    const url = page.url();
    check('sin módulos, el shell desvía a /first-run', /\/first-run$/.test(url), `URL=${url}`);
    const titleVisible = await page.getByTestId('first-run-title').isVisible().catch(() => false);
    const installVisible = await page.getByTestId('first-run-install').isVisible().catch(() => false);
    check('se ve el título y el botón de instalar', titleVisible && installVisible);
    await page.context().close();
  }

  // 2) la pantalla no es una trampa: se puede salir al marketplace
  {
    const page = await newPage(browser, session);
    await page.goto(WEB + '/first-run');
    await page.getByTestId('first-run-marketplace').click();
    await page.waitForURL(/\/marketplace$/, { timeout: 10_000 }).catch(() => {});
    check('se puede escapar al marketplace', /\/marketplace$/.test(page.url()), `URL=${page.url()}`);
    await page.context().close();
  }

  // 3) en cuanto hay un módulo instalado, el shell deja de empujar (instalación REAL, no un stub)
  if (REAL_MODULE_DIR) {
    const res = await fetch(`${RUNTIME}/api/modules/install`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ dir: REAL_MODULE_DIR }),
    });
    const body = await res.text();
    check('instalación real de un módulo', res.ok, `${res.status} ${body}`);
    if (res.ok) {
      const page = await newPage(browser, session);
      await page.goto(WEB + '/');
      await page.waitForURL(/\/dashboard$/, { timeout: 10_000 }).catch(() => {});
      check('con módulos, ya NO desvía (va a /dashboard)', /\/dashboard$/.test(page.url()), `URL=${page.url()}`);
      await page.context().close();
    }
  } else {
    console.log('  – (omitido) define HUB_TEST_MODULE_DIR para probar el caso "con módulos"');
  }
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} OK`);
process.exit(failed.length ? 1 : 0);
