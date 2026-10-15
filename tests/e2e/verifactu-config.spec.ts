// VeriFactu's Configuration and Settings in Chrome, in Spanish (apps/verifactu/WORKBOOK.md), against the real Hub:
//   - VERIFACTU-F02, F03: «Mi certificado» uploads a .p12 made for the test (never a real certificate), shows its
//     holder, NIF and expiry, and removes it after asking;
//   - VERIFACTU-F05: «Lo remite ERPlora» refuses a signed model that is no PDF (by its bytes, not its name) with the
//     Spanish text, and takes four minimal PDFs on to ERPlora's account. The SaaS on `main` has no review app yet
//     (`fiscal/`) and knows no hub with this test's id, so it answers 404 and the Hub says «not linked yet»: the
//     Hub's own checks passed and the documents reached the SaaS. A 201 needs the SaaS's `fiscal/` and a real hub;
//   - VERIFACTU-F08: Settings lists what keeps the business from going live, the missing paid option among it, from
//     the SaaS's photo (`PUT /internal/hubs/{id}/state`, signed as the SaaS signs it), and drops it once paid.
// The photo is the SaaS's, sent here the way the SaaS sends it. What the run changes in VeriFactu's configuration
// is put back after it (or removed, if the run made it).
import { execFileSync } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, HUB_DIR, login, psql, shown } from './helpers';
import { ensureIssuer } from './invoice-helpers';
import { STACK } from './stack';

/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
/** The hub's id in ERPlora as this run's photo says it (no hub of the local SaaS has it). */
const HUB_ID = '0199e6f0-7e2e-7000-8000-00000000e2e5';
/** The issuer `ensureIssuer` sets: a company, so it names its legal representative and proves it. */
const ISSUER_NIF = 'B12345674';
const PASSWORD = 'e2e-secret';
const DIR = mkdtempSync(join(tmpdir(), 'e2e-verifactu-'));
/** Monotonic photo versions: an older one changes nothing. */
let version = Math.floor(Date.now() / 1000);
/** VeriFactu's configuration row before the run, as JSON (`null`: the run makes it and removes it). */
let before: Record<string, unknown> | null = null;

const CONFIG_COLUMNS = [
  'route',
  'representation_status',
  'representation_updated_at',
  'representation_reason',
  'synced_version',
  'synced_at',
  'hub_status',
  'live_paid',
  'hub_id',
];

type Representation = 'none' | 'submitted' | 'approved' | 'returned' | 'revoked';

/** The SaaS's photo of hub `a`: the representation's state, the live option and the account's status. */
async function pushPhoto(representation: Representation, livePaid: boolean): Promise<void> {
  version += 1;
  const body = JSON.stringify({
    hub_id: HUB_ID,
    slug: 'a',
    version,
    status: 'active',
    verifactu: {
      representation: {
        status: representation,
        updated_at: representation === 'none' ? null : new Date().toISOString(),
        reason: '',
      },
      live_paid: livePaid,
    },
  });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', SECRET).update(`${timestamp}.${body}`).digest('hex');
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/hubs/${HUB_ID}/state`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

/** A .p12 made here (self-signed, the issuer's NIF as its organisation identifier), valid for a year. */
function makeP12(path: string): void {
  const script = join(DIR, 'make_p12.py');
  writeFileSync(
    script,
    `import datetime as dt, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

out, password, nif = sys.argv[1], sys.argv[2].encode(), sys.argv[3]
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "E2E PELUQUERIA ANA SL"),
    x509.NameAttribute(NameOID.ORGANIZATION_IDENTIFIER, "VATES-" + nif),
    x509.NameAttribute(NameOID.SERIAL_NUMBER, "12345678Z"),
])
now = dt.datetime.now(dt.UTC)
cert = (
    x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365))
    .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
    .sign(key, hashes.SHA256())
)
data = pkcs12.serialize_key_and_certificates(b"e2e", key, cert, None, serialization.BestAvailableEncryption(password))
open(out, "wb").write(data)
`,
  );
  execFileSync('uv', ['run', 'python', script, path, PASSWORD, ISSUER_NIF], { cwd: HUB_DIR, stdio: 'pipe' });
}

/** The smallest file the Hub takes as a PDF: it reads the bytes, never the name. */
function pdf(name: string): string {
  const path = join(DIR, name);
  writeFileSync(path, `%PDF-1.4\n% ${name}\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n`);
  return path;
}

/** The owner on `a`, in Spanish. */
async function spanishPage(browser: import('@playwright/test').Browser, next: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, next);
  // The Hub's language cookie, the one the sign-in sets from the account.
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}${next}`);
  await page.locator('ion-menu').waitFor({ state: 'attached' });
  return { context, page };
}

function restoreConfig(): void {
  if (before === null) {
    psql('delete from verifactu_owncertificate; delete from verifactu_config');
    return;
  }
  const json = JSON.stringify(before).replaceAll("'", "''");
  const sets = CONFIG_COLUMNS.map((column) => `${column} = r.${column}`).join(', ');
  psql(
    `delete from verifactu_owncertificate; update verifactu_config c set ${sets} from json_populate_record(null::verifactu_config, '${json}'::json) r`,
  );
}

test.beforeAll(async ({ browser }) => {
  const { context } = await spanishPage(browser, '/verifactu/config');
  await ensureIssuer(context);
  await context.close();
  const row = psql(`select row_to_json(c) from verifactu_config c`);
  before = row ? (JSON.parse(row) as Record<string, unknown>) : null;
  psql('delete from verifactu_owncertificate');
});

test.afterAll(() => {
  restoreConfig();
});

test('Mi certificado: upload a .p12, see its holder and expiry, remove it', async ({ browser }) => {
  const p12 = join(DIR, 'negocio.p12');
  makeP12(p12);
  const { context, page } = await spanishPage(browser, '/verifactu/config');
  const view = shown(page);
  await view.locator('[data-testid=verifactu-config-tab-own]').click();
  const own = view.locator('[data-testid=verifactu-config-own]');
  const cert = own.locator('[data-testid=verifactu-config-cert]');
  await expect(cert).toContainText('Sin cargar');

  await own.locator('[data-testid=verifactu-config-cert-file]').setInputFiles(p12);
  await expect(own.locator('[data-testid=verifactu-config-cert-picked]')).toHaveText('negocio.p12');
  await own.locator('[data-testid=verifactu-config-cert-password] input').fill(PASSWORD);
  await own.locator('[data-testid=verifactu-config-cert-upload]').click();

  await expect(cert).toContainText('Cargado');
  await expect(cert).toContainText('E2E PELUQUERIA ANA SL');
  await expect(cert).toContainText(ISSUER_NIF);
  await expect(cert.locator('dt', { hasText: 'Caduca el' })).toBeVisible();
  await expect(cert.locator('dd').last()).toContainText(String(new Date().getFullYear() + 1));
  await expect(own.locator('[data-testid=verifactu-config-cert-error]')).toHaveCount(0);
  expect(psql('select holder_tax_id from verifactu_owncertificate')).toBe(ISSUER_NIF);

  await own.locator('[data-testid=verifactu-config-cert-remove]').click();
  const dialog = page.locator('ion-modal');
  await expect(dialog).toContainText('¿Quitar el certificado?');
  await dialog.locator('ion-button', { hasText: 'Quitar' }).click();
  await expect(cert).toContainText('Sin cargar');
  await expect(cert).not.toContainText(ISSUER_NIF);
  expect(psql('select count(*) from verifactu_owncertificate')).toBe('0');
  await context.close();
});

test('Lo remite ERPlora: a signed model that is no PDF is refused in Spanish; four PDFs go on to the SaaS', async ({ browser }) => {
  await pushPhoto('none', false);
  const { context, page } = await spanishPage(browser, '/verifactu/config');
  const grant = shown(page).locator('[data-testid=verifactu-config-erplora]');
  await expect(grant.locator('[data-testid=verifactu-grant-form]')).toBeVisible();
  await expect(grant.locator('[data-testid=verifactu-grant-not-linked]')).toHaveCount(0);
  await expect(grant.locator('[data-testid=verifactu-grant-taxpayer]')).toContainText(ISSUER_NIF);

  await grant.locator('[data-testid=verifactu-grant-signer-name] input').fill('Ana Pérez');
  await grant.locator('[data-testid=verifactu-grant-signer-nif] input').fill('X1234567L');
  await grant.locator('[data-testid=verifactu-grant-document-type]').click();
  await page.locator('ion-popover ion-radio').filter({ hasText: /^\s*NIE\s*$/ }).click();
  await expect(grant.locator('[data-testid=verifactu-grant-file-signature_sample]')).toHaveCount(1);

  // Named .pdf, but its bytes are no PDF.
  const fake = join(DIR, 'modelo-firmado.pdf');
  writeFileSync(fake, 'Esto no es un PDF.\n');
  await grant.locator('[data-testid=verifactu-grant-file-signed_model]').setInputFiles(fake);
  await grant.locator('[data-testid=verifactu-grant-file-id_copy]').setInputFiles(pdf('nie.pdf'));
  await grant.locator('[data-testid=verifactu-grant-file-signature_sample]').setInputFiles(pdf('firma.pdf'));
  await grant.locator('[data-testid=verifactu-grant-file-representation_proof]').setInputFiles(pdf('escritura.pdf'));
  const submit = grant.locator('[data-testid=verifactu-grant-submit]');
  await expect(submit).not.toHaveAttribute('aria-disabled', 'true');

  const refused = page.waitForResponse((r) => r.url().endsWith('/api/verifactu/representation') && r.request().method() === 'POST');
  await submit.click();
  const refusal = await refused;
  expect(refusal.status()).toBe(422);
  expect(((await refusal.json()) as { error: { code: string } }).error.code).toBe('fiscal.signed_model_not_pdf');
  const error = grant.locator('[data-testid=verifactu-grant-error]');
  await expect(error).toHaveText('El modelo firmado tiene que ser un PDF — escanéalo o fírmalo con AutoFirma.');

  await grant.locator('[data-testid=verifactu-grant-file-signed_model]').setInputFiles(pdf('modelo-firmado-bien.pdf'));
  await expect(grant.locator('[data-testid=verifactu-grant-picked-signed_model]')).toHaveText('modelo-firmado-bien.pdf');
  const forwarded = page.waitForResponse((r) => r.url().endsWith('/api/verifactu/representation') && r.request().method() === 'POST');
  await submit.click();
  const answer = await forwarded;
  // Past every check of the Hub (a 422 otherwise): the SaaS was asked and knows no hub with this id.
  expect(answer.status()).toBe(409);
  expect(((await answer.json()) as { error: { code: string } }).error.code).toBe('verifactu.hub_unregistered');
  await expect(error).toHaveText('ERPlora todavía no ha vinculado este negocio. Inténtalo en unos minutos.');
  await context.close();
});

test('Ajustes: the missing paid option keeps the business from going live until the photo says it is paid', async ({ browser }) => {
  await pushPhoto('approved', false);
  const { context, page } = await spanishPage(browser, '/verifactu/settings');
  const view = shown(page);
  const blockers = view.locator('[data-testid=verifactu-settings-live-blockers]');
  await expect(blockers).toContainText('Todavía no puede pasar a producción:');
  await expect(blockers).toContainText('la opción en vivo de VeriFactu no está en tu plan: añádela en tu cuenta de ERPlora');
  await expect(blockers).not.toContainText('falta que ERPlora apruebe tu autorización firmada');
  await expect(view.locator('[data-testid=verifactu-settings-go-live]')).toHaveAttribute('aria-disabled', 'true');

  // The live result follows the next photo, without reloading.
  await pushPhoto('approved', true);
  await expect(blockers).toHaveCount(0);
  // Still closed: this server has not opened production (VERIFACTU_PRODUCTION_ENABLED, prod only).
  await expect(view.locator('[data-testid=verifactu-settings-closed]')).toBeVisible();
  await expect(view.locator('[data-testid=verifactu-settings-go-live]')).toHaveAttribute('aria-disabled', 'true');
  await context.close();
});
