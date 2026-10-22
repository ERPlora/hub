// flow: WHATSAPP_INBOX-F01, WHATSAPP_INBOX-F02
// «Connect WhatsApp» and «Reconnect» pressed in the inbox's Settings, in a hidden Chrome, against the run's real
// erplora.com (`SAAS_URL`): its door 10 gives Meta's app and its return page (`GET /whatsapp/return`), the Hub opens
// Meta's window, erplora.com's page brings Meta's one-time code back to the Hub, and the Hub has erplora.com (door 11)
// connect the number. In development erplora.com runs over plain http: the Hub takes that return page because it is
// its own SAAS_URL's origin, and only with DEBUG (`_return_page` in services.py).
//
// Only Meta is played, at its two ends:
// - its dialog (`https://www.facebook.com/<version>/dialog/oauth`), served by the browser's route: as Meta's window
//   does, it posts the account and the number chosen (`WA_EMBEDDED_SIGNUP`, from facebook.com's origin) to the Hub's
//   page and sends the window to the dialog's `redirect_uri` with a code and the Hub's `state` (or Meta's refusal);
// - its Graph API, which erplora.com calls in door 11 to exchange the code: a TLS endpoint of this spec for
//   `graph.facebook.com` only, reached by erplora.com through `HTTPS_PROXY=http://127.0.0.1:<hub port + 9>` and
//   trusted with `SSL_CERT_FILE=<this checkout>/tests/e2e/.artifacts/meta-graph-<hub port>/ca.pem` (environment
//   only, set when erplora.com starts: its code is not touched; the certificate is made by this spec, before the
//   first call). It answers as Meta does in erplora.com's own whatsapp/tests/test_internal_connect.py.
// Besides those two, erplora.com runs as whatsapp-helpers.ts says (the e2e Meta app, `HUB_INTERNAL_URL` to this Hub,
// its own database) with `WHATSAPP_REDIRECT_URI=<SAAS_URL>/whatsapp/return`.
//
// F01: not connected, Settings offers «Connect WhatsApp»; the window brings the code back and the number is connected,
// without reloading; Meta's cancelled window and an expired code connect nothing and say why. F02: with «Needs
// reconnecting», the inbox's notice leads to Settings, «Reconnect» opens the same window and connects the number
// again, and the inbox's notice goes by itself (disconnecting: whatsapp-inbox-connect.spec.ts).
// Captures, three sizes: FIX-HUB-WHATSAPP-INBOX-LOCAL-HTTP-RETURN-PAGE-REFUSED[-F01|-F02]-390|834|1440.
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { createServer as createHttpServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { createServer as createHttpsServer } from 'node:https';
import type { Socket } from 'node:net';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, ARTIFACTS, HUB_DIR, login, SAAS, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { STACK } from './stack';
import { cleanUp, NUMBER_ID, pushChannel, seedErplora, WABA_ID } from './whatsapp-helpers';

const TASK = 'FIX-HUB-WHATSAPP-INBOX-LOCAL-HTTP-RETURN-PAGE-REFUSED';
const RETURN_PAGE = `${SAAS}/whatsapp/return`;
const GRAPH_HOST = 'graph.facebook.com';
const GRAPH_PORT = STACK.hubPort + 9;
const CERTS = join(ARTIFACTS, `meta-graph-${STACK.hubPort}`);

/** The codes Meta's window gives in this spec, and what Meta answers when erplora.com exchanges each one. */
const CODE = 'AQBe2e-one-time-code_ok';
const EXPIRED_CODE = 'AQBe2e-one-time-code_expired';
const TOKEN = 'EAAGe2e-business-token';
const BUSINESS_ID = '880000000000102';
const SHOWN_NUMBER = '+34910000101';
const SHOWN_NAME = 'E2E Peluquería';
/** Meta's refusal of an expired code (erplora.com's tests: `OAUTH_ERROR`). */
const OAUTH_ERROR = {
  error: { message: 'This authorization code has expired.', type: 'OAuthException', code: 100, error_subcode: 36007, fbtrace_id: 'A1' },
};

/** What erplora.com asked Meta's Graph: the method, the path without its version and the query. */
interface GraphCall {
  method: string;
  path: string;
  query: Record<string, string>;
}

/** Meta's Graph as erplora.com's door 11 meets it: the code exchanged, the token's expiry, the account's numbers,
 *  the app subscribed and the number registered. */
function graphAnswer(call: GraphCall): [number, unknown] {
  const route = `${call.method} ${call.path}`;
  if (route === 'GET /oauth/access_token') {
    return call.query.code === CODE ? [200, { access_token: TOKEN, token_type: 'bearer' }] : [400, OAUTH_ERROR];
  }
  if (route === 'GET /debug_token') return [200, { data: { is_valid: true, expires_at: 0 } }];
  if (route === `GET /${WABA_ID}/phone_numbers`) {
    return [200, { data: [{ id: NUMBER_ID, display_phone_number: '+34 910 00 01 01', verified_name: SHOWN_NAME }] }];
  }
  if (route === `POST /${WABA_ID}/subscribed_apps` || route === `POST /${NUMBER_ID}/register`) return [200, { success: true }];
  return [400, { error: { message: `Unsupported request: ${route}.`, type: 'GraphMethodException', code: 100 } }];
}

/** A certificate authority of this run and `graph.facebook.com`'s certificate signed by it (what erplora.com's
 *  `SSL_CERT_FILE` trusts), made with the Hub's `cryptography`. */
const MAKE_CERTS = `
import datetime, pathlib, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
now = datetime.datetime.now(datetime.UTC)
usage = dict(content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False,
             encipher_only=False, decipher_only=False)
ca_key, key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "e2e Meta Graph CA")])
def base(subject, public):
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name).public_key(public)
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(hours=1))
            .not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(public), critical=False))
ca = (base(ca_name, ca_key.public_key())
      .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
      .add_extension(x509.KeyUsage(digital_signature=False, key_cert_sign=True, crl_sign=True, **usage), critical=True)
      .sign(ca_key, hashes.SHA256()))
leaf = (base(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "${GRAPH_HOST}")]), key.public_key())
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("${GRAPH_HOST}")]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=False, crl_sign=False, **usage), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256()))
(out / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
(out / "cert.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
(out / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                serialization.NoEncryption()))
`;

/** Meta's Graph, for erplora.com only: an HTTP proxy on `GRAPH_PORT` that tunnels `graph.facebook.com:443` (and
 *  nothing else) to a TLS server answering `graphAnswer`; every call is kept in `calls`. */
async function startGraph(calls: GraphCall[]): Promise<Server> {
  execFileSync('uv', ['run', 'python', '-c', MAKE_CERTS, CERTS], { cwd: HUB_DIR, encoding: 'utf8' });
  const graph = createHttpsServer(
    { cert: readFileSync(join(CERTS, 'cert.pem')), key: readFileSync(join(CERTS, 'key.pem')) },
    (request: IncomingMessage, response: ServerResponse) => {
      request.resume();
      request.on('end', () => {
        const url = new URL(request.url ?? '/', `https://${GRAPH_HOST}`);
        const call = {
          method: request.method ?? 'GET',
          path: url.pathname.replace(/^\/v\d+\.\d+/, ''),
          query: Object.fromEntries(url.searchParams),
        };
        calls.push(call);
        const [status, body] = graphAnswer(call);
        response.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(body));
      });
    },
  );
  const proxy = createHttpServer((_request, response) => response.writeHead(403).end());
  proxy.on('connect', (request: IncomingMessage, socket: Socket, head: Buffer) => {
    if (request.url !== `${GRAPH_HOST}:443`) {
      socket.end('HTTP/1.1 403 Forbidden\r\n\r\n');
      return;
    }
    socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
    if (head.length) socket.unshift(head);
    graph.emit('connection', socket);
  });
  proxy.on('close', () => graph.close());
  await new Promise<void>((resolve, reject) => {
    proxy.once('error', reject);
    proxy.listen(GRAPH_PORT, '127.0.0.1', () => resolve());
  });
  return proxy;
}

/** How Meta's window ends: what it posts from facebook.com meanwhile (`session`, its `event` and `data`) and what it
 *  sends back to the return page besides the Hub's state (`back`: a code, or Meta's refusal). */
interface MetaEnd {
  session?: { event: string; data: Record<string, string> };
  back: Record<string, string>;
}

/** Meta's dialog, the only page played: every dialog the Hub opens is kept in `dialogs`. */
async function playMeta(context: BrowserContext, end: MetaEnd, dialogs: URL[]): Promise<void> {
  await context.unroute('https://www.facebook.com/**');
  await context.route('https://www.facebook.com/**', async (route) => {
    const asked = new URL(route.request().url());
    dialogs.push(asked);
    const back = new URL(asked.searchParams.get('redirect_uri') ?? '');
    for (const [key, value] of Object.entries(end.back)) back.searchParams.set(key, value);
    back.searchParams.set('state', asked.searchParams.get('state') ?? '');
    const session = end.session ? JSON.stringify({ type: 'WA_EMBEDDED_SIGNUP', ...end.session }) : null;
    await route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: `<!doctype html><title>Meta</title><script>
const session = ${JSON.stringify(session)};
if (session && window.opener) window.opener.postMessage(session, ${JSON.stringify(A)});
location.replace(${JSON.stringify(back.toString())});
</script>`,
    });
  });
}

const FINISHED = { event: 'FINISH', data: { waba_id: WABA_ID, phone_number_id: NUMBER_ID, business_id: BUSINESS_ID } };
const number = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-number]');
const connectButton = (page: Page) => number(page).locator('[data-testid=whatsapp-inbox-number-connect]');

/** Settings of `a`, once the Hub has asked erplora.com (door 10) what opens Meta's window: its answer. */
async function openSettings(page: Page): Promise<Record<string, unknown>> {
  const asked = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/prepare'));
  await login(page, A, '/whatsapp_inbox/settings');
  const answer = await asked;
  expect(answer.status()).toBe(200);
  return (await answer.json()) as Record<string, unknown>;
}

/** Presses the connect button (`label`) and waits until Meta's window has closed itself. */
async function pressAndFinish(page: Page, label: string): Promise<void> {
  await expect(connectButton(page)).toHaveText(label);
  const opened = page.waitForEvent('popup');
  await connectButton(page).click();
  const window = await opened;
  if (!window.isClosed()) await window.waitForEvent('close', { timeout: 15_000 });
}

/** How many rows at the bottom of `png` repeat its first rows (0: none): what a capture taken before the browser
 *  painted the page at its new size shows (erplora.com's e2e, `repeatedTop` of its tests/e2e/panel/fixtures.ts). A
 *  stripe of one flat colour does not count. Decoded in the page's browser: the e2e has no image library. */
async function repeatedTop(page: Page, png: Buffer): Promise<number> {
  return page.evaluate(async (base64) => {
    const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
    const { width, height } = bitmap;
    const context = new OffscreenCanvas(width, height).getContext('2d');
    if (!context) throw new Error('repeatedTop: no 2d context to read the screenshot');
    context.drawImage(bitmap, 0, 0);
    const pixels = new Uint32Array(context.getImageData(0, 0, width, height).data.buffer);
    const sameRow = (a: number, b: number) => {
      for (let x = 0; x < width; x++) if (pixels[a * width + x] !== pixels[b * width + x]) return false;
      return true;
    };
    const flatRow = (row: number) => {
      for (let x = 1; x < width; x++) if (pixels[row * width + x] !== pixels[row * width]) return false;
      return true;
    };
    for (let rows = Math.floor(height / 2); rows >= 8; rows--) {
      let repeated = true;
      let flat = true;
      for (let row = 0; row < rows && repeated; row++) {
        repeated = sameRow(height - rows + row, row);
        flat &&= flatRow(row);
      }
      if (repeated && !flat) return rows;
    }
    return 0;
  }, png.toString('base64'));
}

const nextFrames = (page: Page) =>
  page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));

/** `page` in the three sizes once `ready` holds in each: painted at that size (taken again until it is) and without
 *  sideways scroll. */
async function shots(page: Page, name: string, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    // The pointer stays where the last button was pressed: away, so no hover is captured.
    await page.mouse.move(0, viewport.height - 1);
    await ready(page);
    await settled(page);
    await noHorizontalScroll(page, `${name} ${viewport.label}`);
    let png = await page.screenshot();
    for (let tries = 0; tries < 10 && (await repeatedTop(page, png)) > 0; tries++) {
      await nextFrames(page);
      png = await page.screenshot();
    }
    expect(await repeatedTop(page, png), `${name} ${viewport.label} painted at its size`).toBe(0);
    writeFileSync(shot(`${name}-${viewport.label}`), png);
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

test.describe.configure({ mode: 'serial' });

const graphCalls: GraphCall[] = [];
let graph: Server | undefined;

test.beforeAll(async () => {
  graph = await startGraph(graphCalls);
  // erplora.com knows `a` (its test seed, with `a`'s number) and this Hub takes its photo.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
});

test.afterAll(async () => {
  cleanUp();
  if (graph) await new Promise((resolve) => graph?.close(resolve));
});

test.beforeEach(() => {
  graphCalls.length = 0;
});

test('WHATSAPP_INBOX-F01: «Connect WhatsApp» opens Meta’s window, erplora.com’s page brings the code back and the number is connected', async ({
  page,
  context,
}) => {
  pushChannel({ status: 'not_connected' });
  const prepared = await openSettings(page);

  // erplora.com's door 10 gives its own (http, development) return page, and the Hub offers the window.
  expect(prepared).toMatchObject({ available: true, reason: null, redirect_uri: RETURN_PAGE });
  await expect(number(page)).toContainText('Not connected');
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-unavailable]')).toHaveCount(0);
  await shots(page, TASK, async (p) => {
    await expect(connectButton(p)).toBeVisible();
  });

  const dialogs: URL[] = [];
  await playMeta(context, { session: FINISHED, back: { code: CODE } }, dialogs);
  const connected = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/connect'));
  await pressAndFinish(page, 'Connect WhatsApp');

  // The window was Meta's, with erplora.com's app and return page and a state of this business's.
  expect(dialogs).toHaveLength(1);
  expect(dialogs[0].searchParams.get('redirect_uri')).toBe(RETURN_PAGE);
  expect(dialogs[0].searchParams.get('client_id')).toBe(prepared.app_id);
  expect(dialogs[0].searchParams.get('state')).toMatch(/^a\.[0-9a-f]{32}$/);
  // erplora.com's door 11 exchanged the code the return page brought back, with that same return page (Meta's rule).
  const answer = await connected;
  expect(answer.status()).toBe(200);
  expect(await answer.json()).toEqual({
    connected: true,
    phone_number: SHOWN_NUMBER,
    display_name: SHOWN_NAME,
    history_requested: false,
  });
  const exchange = graphCalls.find((call) => call.path === '/oauth/access_token');
  expect(exchange?.query).toMatchObject({ code: CODE, redirect_uri: RETURN_PAGE });
  expect(graphCalls.map((call) => `${call.method} ${call.path}`)).toContain(`POST /${NUMBER_ID}/register`);

  // «Your number» says it at once, without reloading.
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-done]')).toHaveText(
    `WhatsApp connected: ${SHOWN_NUMBER} (${SHOWN_NAME}).`,
  );
  await expect(number(page)).toContainText('Connected');
  await expect(connectButton(page)).toHaveCount(0);
  await shots(page, `${TASK}-F01`, async (p) => {
    await expect(number(p).locator('[data-testid=whatsapp-inbox-number-done]')).toBeVisible();
  });
});

test('WHATSAPP_INBOX-F01: Meta’s window cancelled connects nothing and says Meta’s reason', async ({ page, context }) => {
  pushChannel({ status: 'not_connected' });
  await openSettings(page);
  let connectAsked = false;
  page.on('request', (request) => {
    if (request.url().endsWith('/api/whatsapp_inbox/channel/connect')) connectAsked = true;
  });

  await playMeta(context, { back: { error: 'access_denied', error_description: 'Permissions error' } }, []);
  await pressAndFinish(page, 'Connect WhatsApp');

  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-failed]')).toHaveText(
    'Meta did not finish the connection: Permissions error',
  );
  await expect(number(page)).toContainText('Not connected');
  await expect(connectButton(page)).toBeVisible();
  expect(connectAsked).toBe(false);
  expect(graphCalls).toEqual([]);
});

test('WHATSAPP_INBOX-F01: an expired code is Meta’s refusal, said through erplora.com, and nothing is connected', async ({
  page,
  context,
}) => {
  pushChannel({ status: 'not_connected' });
  await openSettings(page);

  await playMeta(context, { session: FINISHED, back: { code: EXPIRED_CODE } }, []);
  const refused = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/connect'));
  await pressAndFinish(page, 'Connect WhatsApp');

  const answer = await refused;
  expect(answer.status()).toBe(409);
  expect(((await answer.json()) as { error: { code: string } }).error.code).toBe('whatsapp_inbox.meta_rejected');
  expect(graphCalls.map((call) => `${call.method} ${call.path}`)).toEqual(['GET /oauth/access_token']);
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-failed]')).toHaveText(
    'Meta did not accept the connection: This authorization code has expired.',
  );
  await expect(number(page)).toContainText('Not connected');
});

test('WHATSAPP_INBOX-F02: the inbox’s notice leads to «Reconnect», which opens the same window, and the notice goes by itself', async ({
  page,
  context,
}) => {
  pushChannel({ status: 'reconnect_needed' });
  await login(page, A, '/whatsapp_inbox/inbox');
  const notice = shown(page).locator('[data-testid=whatsapp-inbox-reconnect]');
  await expect(notice).toBeVisible();

  // The inbox's notice takes whoever can configure to Settings, which asks erplora.com what opens Meta's window.
  const asked = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/prepare'));
  await notice.locator('[data-testid=whatsapp-inbox-go-to-settings]').click();
  await expect(page).toHaveURL(/\/whatsapp_inbox\/settings$/);
  expect(await (await asked).json()).toMatchObject({ available: true, redirect_uri: RETURN_PAGE });
  await expect(number(page)).toContainText('Needs reconnecting');
  await expect(number(page)).toContainText('WhatsApp withdrew the permission: reconnect the number.');
  await shots(page, `${TASK}-F02`, async (p) => {
    await expect(connectButton(p)).toBeVisible();
  });

  await playMeta(context, { session: FINISHED, back: { code: CODE } }, []);
  const connected = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/connect'));
  await pressAndFinish(page, 'Reconnect');

  expect((await connected).status()).toBe(200);
  expect(graphCalls.find((call) => call.path === '/oauth/access_token')?.query).toMatchObject({ code: CODE });
  await expect(number(page).locator('[data-testid=whatsapp-inbox-number-done]')).toHaveText(
    `WhatsApp connected: ${SHOWN_NUMBER} (${SHOWN_NAME}).`,
  );
  await expect(number(page)).toContainText('Connected');
  await expect(number(page)).not.toContainText('Needs reconnecting');

  // Back in the inbox, without reloading: the notice is gone.
  await shown(page).locator('[data-testid=tab-inbox]').click();
  await expect(page).toHaveURL(/\/whatsapp_inbox\/inbox$/);
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-reconnect]')).toHaveCount(0);
});
