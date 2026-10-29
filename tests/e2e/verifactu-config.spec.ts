// VeriFactu's Configuration and Settings in Chrome, in Spanish (apps/verifactu/WORKBOOK.md), against the real Hub:
//   - VERIFACTU-F02, F03: «Mi certificado» uploads a .p12 made for the test (never a real certificate), shows its
//     holder, NIF and expiry, and removes it after asking;
//   - VERIFACTU-F05: «Lo remite ERPlora» refuses a signed model that is no PDF (by its bytes, not its name) with the
//     Spanish text, and takes four minimal PDFs on to ERPlora's account. The spec points VeriFactu at a hub id no
//     SaaS registered (`unknownToTheSaas`), so the SaaS answers 404 and the Hub says «not linked yet»: the Hub's own
//     checks passed and the documents reached the SaaS. A 201 needs a hub the SaaS registered, and the SaaS of the
//     run may know `a` by its own id (WhatsApp's seed, `whatsapp_hub_seed.py`, registers it there);
//   - VERIFACTU-F05: «Descargar el modelo» downloads the SaaS's model with the issuer of Invoicing (legal name, NIF and
//     address) already written in its blanks: the query signed by v2, as the SaaS verifies it, or a 401 and no PDF;
//   - VERIFACTU-F06: an authorisation in review offers «Volver a enviar», which opens the form again with what the new
//     sending does to the one in review;
//   - VERIFACTU-F04: «Usar mi propio certificado» in Settings chooses who files: the own certificate once it is
//     loaded, ERPlora's seal again when switched off;
//   - VERIFACTU-F08: Settings lists what keeps the business from going live, the authorisation in review among it,
//     from the SaaS's photo (`PUT /internal/hubs/{id}/state`, signed as the SaaS signs it), and drops it once approved;
//     no plan option is ever among them (PLAN §30, round 2026-10-22b: VeriFactu on Free).
// Each flow leaves its evidence in the three sizes of the migration (`APP-VERIFACTU-<flow>-390|834|1440`).
// The photo is the SaaS's, sent here the way the SaaS sends it, to `a`'s row of the registry (`base_hub`). What the
// run changes in VeriFactu's configuration, the own certificate and that row's photo is put back after it (or
// removed, if the run made it), and so is the issuer.
import { execFileSync } from 'node:child_process';
import { createHmac, randomUUID } from 'node:crypto';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { inflateSync } from 'node:zlib';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, HUB_DIR, login, psql, shot, shown, topbarApps } from './helpers';
import { cleanInvoices, ensureIssuer, FLOW_VIEWPORTS, type IssuerOut, snapshotSeries } from './invoice-helpers';
import { STACK } from './stack';

/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
/** The id of `a` in the registry (`base_hub`), the one `/internal/hubs/{id}/state` takes; read before the first
 *  test. `seed_local_hubs` gives each database its own, so a fixed id was answered 404 «No hub has this id.» once
 *  the registry came (hub#63). */
let hubId = '';
/** The issuer `ensureIssuer` sets: a company, so it names its legal representative and proves it. */
const ISSUER_NIF = 'B12345674';
/** The issuer the run works with (the hub's own when it already had one), read before the first test. */
let issuer: IssuerOut;
const PASSWORD = 'e2e-secret';
const DIR = mkdtempSync(join(tmpdir(), 'e2e-verifactu-'));
/** Monotonic photo versions: an older one changes nothing. */
let version = Math.floor(Date.now() / 1000);
/** Whether VeriFactu's configuration row existed before the run (if not, the run makes it and removes it). */
let hadConfig = true;
/** The copies the run keeps of what it changes: VeriFactu's configuration and the own certificate. */
const BACKUP = {
  config: 'e2e_verifactu_config_before',
  certificate: 'e2e_verifactu_owncertificate_before',
  photo: 'e2e_base_hub_photo_before',
};

const CONFIG_COLUMNS = [
  'route',
  'representation_status',
  'representation_updated_at',
  'representation_reason',
  'synced_version',
  'synced_at',
  'hub_status',
  'hub_id',
];

type Representation = 'none' | 'submitted' | 'approved' | 'returned' | 'revoked';

/** The page in the three sizes, as `APP-VERIFACTU-<flow>-<size>`, each once `ready` says it painted. */
async function flowShots(page: Page, flow: string, ready: (page: Page) => Promise<void>): Promise<void> {
  const restore = page.viewportSize() ?? { width: 1280, height: 860 };
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await page.screenshot({ path: shot(`APP-VERIFACTU-${flow}-${viewport.label}`) });
  }
  await page.setViewportSize(restore);
}

/** The SaaS's photo of hub `a`: the representation's state and the account's status. */
async function pushPhoto(representation: Representation): Promise<void> {
  version += 1;
  const body = JSON.stringify({
    hub_id: hubId,
    slug: 'a',
    version,
    status: 'active',
    verifactu: {
      representation: {
        status: representation,
        updated_at: representation === 'none' ? null : new Date().toISOString(),
        reason: '',
      },
    },
  });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', SECRET).update(`${timestamp}.${body}`).digest('hex');
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/hubs/${hubId}/state`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

/** Points VeriFactu at a hub id made here, one no SaaS registered, so the SaaS answers it 404 whatever seed ran there
 *  before: WhatsApp's (`whatsapp_hub_seed.py`) registers `a` with this Hub's own id, and the photo hands VeriFactu
 *  that id. The next photo puts `a`'s back, and `restoreConfig` the one before the run. */
function unknownToTheSaas(): void {
  psql(`update verifactu_config set hub_id = '${randomUUID()}'`);
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

/** The texts a PDF writes with `(…) Tj`, its literal strings decoded (escapes and octal codes, Windows-1252 read as
 *  Latin-1: every Spanish letter is the same byte), from every stream, raw or deflated. */
function pdfTexts(file: Buffer): string[] {
  const raw = file.toString('latin1');
  const contents: string[] = [];
  for (const stream of raw.matchAll(/stream\r?\n([\s\S]*?)\r?\nendstream/g)) {
    const bytes = Buffer.from(stream[1], 'latin1');
    contents.push(stream[1]);
    try {
      contents.push(inflateSync(bytes).toString('latin1'));
    } catch {
      // Not deflated (the merged page's content is written raw): read as it is above.
    }
  }
  const escapes: Record<string, string> = { n: '\n', r: '\r', t: '\t', b: '\b', f: '\f' };
  return contents.flatMap((content) =>
    [...content.matchAll(/\(((?:\\[\s\S]|[^\\)])*)\)\s*Tj/g)].map((literal) =>
      literal[1].replace(/\\([0-7]{1,3}|[\s\S])/g, (_, code: string) =>
        /^[0-7]+$/.test(code) ? String.fromCharCode(parseInt(code, 8)) : (escapes[code] ?? code),
      ),
    ),
  );
}

/** The owner on `a`, in Spanish. */
async function spanishPage(browser: import('@playwright/test').Browser, next: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, next);
  // The Hub's language cookie, the one the sign-in sets from the account.
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}${next}`);
  await topbarApps(page).waitFor({ state: 'visible' });
  return { context, page };
}

/** The id of `a` in the registry; the e2e's global setup already refused a run without it. */
function registryIdOfA(): string {
  const id = psql("select id from base_hub where slug = 'a'");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id)) {
    throw new Error(`The registry of DB_NAME=${STACK.database} has no hub a (got ${JSON.stringify(id)}): run node tests/e2e/database.ts.`);
  }
  return id;
}

/** Copies the configuration, the own certificate and `a`'s photo aside (tables of the database, so a shell's quoting
 *  never touches their values) and starts from no certificate. */
function backUpConfig(): void {
  hubId = registryIdOfA();
  hadConfig = psql('select count(*) from verifactu_config') !== '0';
  // Past the version the hub already applied, or the run's photos would change nothing.
  version = Math.max(
    version,
    Number(psql('select coalesce(max(synced_version), 0) from verifactu_config')),
    Number(psql(`select state_version from base_hub where id = '${hubId}'`)),
  );
  psql(
    [
      `drop table if exists ${BACKUP.config}`,
      `drop table if exists ${BACKUP.certificate}`,
      `drop table if exists ${BACKUP.photo}`,
      `create table ${BACKUP.config} as select * from verifactu_config`,
      `create table ${BACKUP.certificate} as select * from verifactu_owncertificate`,
      `create table ${BACKUP.photo} as select id, state, state_version from base_hub where id = '${hubId}'`,
      'delete from verifactu_owncertificate',
    ].join('; '),
  );
}

/** Puts back what `backUpConfig` copied: the configuration's columns the run moves, the certificate and `a`'s photo. */
function restoreConfig(): void {
  const sets = CONFIG_COLUMNS.map((column) => `${column} = b.${column}`).join(', ');
  psql(
    [
      'delete from verifactu_owncertificate',
      `insert into verifactu_owncertificate select * from ${BACKUP.certificate}`,
      hadConfig
        ? `update verifactu_config c set ${sets} from ${BACKUP.config} b where b.id = c.id`
        : 'delete from verifactu_config where not exists (select 1 from verifactu_record)',
      `update base_hub h set state = b.state, state_version = b.state_version from ${BACKUP.photo} b where b.id = h.id`,
      `drop table ${BACKUP.config}`,
      `drop table ${BACKUP.certificate}`,
      `drop table ${BACKUP.photo}`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  snapshotSeries();
  backUpConfig();
  const { context } = await spanishPage(browser, '/verifactu/config');
  issuer = await ensureIssuer(context);
  await context.close();
});

test.afterAll(() => {
  restoreConfig();
  // The issuer the run set up, when the hub had none (and the numbering, untouched here).
  cleanInvoices();
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
  for (const flow of ['F02', 'F34']) {
    // F34: the renewed one is uploaded the same way; what it shows is its holder and «Caduca el».
    await flowShots(page, flow, async (p) => {
      await expect(shown(p).locator('[data-testid=verifactu-config-cert]')).toContainText('Cargado');
    });
  }

  await own.locator('[data-testid=verifactu-config-cert-remove]').click();
  // By its title: the shell keeps other dialogs in the page (the apps launcher is an ion-modal too).
  const dialog = page.locator('ion-modal', { hasText: '¿Quitar el certificado?' });
  await expect(dialog).toBeVisible();
  await dialog.locator('ion-button', { hasText: 'Quitar' }).click();
  await expect(dialog).toBeHidden();
  await expect(cert).toContainText('Sin cargar');
  await expect(cert).not.toContainText(ISSUER_NIF);
  expect(psql('select count(*) from verifactu_owncertificate')).toBe('0');
  await flowShots(page, 'F03', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-config-cert]')).toContainText('Sin cargar');
  });
  await context.close();
});

test('Lo remite ERPlora: a signed model that is no PDF is refused in Spanish; four PDFs go on to the SaaS', async ({ browser }) => {
  await pushPhoto('none');
  unknownToTheSaas();
  const { context, page } = await spanishPage(browser, '/verifactu/config');
  const grant = shown(page).locator('[data-testid=verifactu-config-erplora]');
  await expect(grant.locator('[data-testid=verifactu-grant-form]')).toBeVisible();
  await expect(grant.locator('[data-testid=verifactu-grant-not-linked]')).toHaveCount(0);
  await expect(grant.locator('[data-testid=verifactu-grant-taxpayer]')).toContainText(ISSUER_NIF);
  await flowShots(page, 'F05', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-grant-form]')).toBeVisible();
  });

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
  // Past every check of the Hub (a 422 otherwise): the SaaS was asked and knows no hub with this id (`unknownToTheSaas`).
  expect(answer.status()).toBe(409);
  expect(((await answer.json()) as { error: { code: string } }).error.code).toBe('verifactu.hub_unregistered');
  await expect(error).toHaveText('ERPlora todavía no ha vinculado este negocio. Inténtalo en unos minutos.');
  await context.close();
});

test('VERIFACTU-F05: «Descargar el modelo» downloads the model with the business of Invoicing already written in', async ({ browser }) => {
  await pushPhoto('none');
  const { context, page } = await spanishPage(browser, '/verifactu/config');
  const grant = shown(page).locator('[data-testid=verifactu-config-erplora]');
  await expect(grant.locator('[data-testid=verifactu-grant-form]')).toBeVisible();

  const downloaded = page.waitForEvent('download');
  await grant.locator('[data-testid=verifactu-grant-download]').click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe('anexo-i-otorgamiento-representacion-erplora.pdf');
  await expect(grant.locator('[data-testid=verifactu-grant-downloaded]')).toBeVisible();
  await expect(grant.locator('[data-testid=verifactu-grant-error]')).toHaveCount(0);

  // The real SaaS wrote them: it reads the query only when the v2 signature covers it (401 and no PDF otherwise).
  const model = readFileSync(await download.path());
  expect(model.subarray(0, 4).toString('latin1')).toBe('%PDF');
  const written = pdfTexts(model);
  for (const value of [issuer.legal_name, issuer.tax_id, issuer.city, issuer.address]) {
    expect(written, `the model carries «${value}»`).toContain(value);
  }
  await context.close();
});

test('Ajustes: the authorisation in review keeps the business from going live until the photo says it is approved; the closed server still does', async ({ browser }) => {
  await pushPhoto('submitted');
  const { context, page } = await spanishPage(browser, '/verifactu/settings');
  const view = shown(page);
  const blockers = view.locator('[data-testid=verifactu-settings-live-blockers]');
  await expect(blockers).toContainText('Todavía no puede pasar a producción:');
  await expect(blockers).toContainText('falta que ERPlora apruebe tu autorización firmada para remitir en producción');
  await expect(view.locator('[data-testid=verifactu-settings-go-live]')).toHaveAttribute('aria-disabled', 'true');
  await flowShots(page, 'F08', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-settings-live-blockers]')).toBeVisible();
  });

  // The live result follows the next photo, without reloading: the approval is all ERPlora's route needs.
  await pushPhoto('approved');
  await expect(blockers).not.toContainText('falta que ERPlora apruebe tu autorización firmada');
  // Still closed: this server has not opened production (VERIFACTU_PRODUCTION_ENABLED, prod only), and that is one
  // more of the reasons listed, not a notice of its own.
  await expect(blockers).toContainText('ERPlora todavía no ha abierto la presentación real a la AEAT en este servidor');
  await expect(view.locator('[data-testid=verifactu-settings-go-live]')).toHaveAttribute('aria-disabled', 'true');
  await context.close();
});

test('VERIFACTU-F06: an authorisation in review offers «Volver a enviar», which says what the new sending does', async ({ browser }) => {
  await pushPhoto('submitted');
  const { context, page } = await spanishPage(browser, '/verifactu/config');
  const grant = shown(page).locator('[data-testid=verifactu-config-erplora]');
  // In review, the form is closed: «Volver a enviar» opens it, with its notice and «Cancelar».
  await expect(grant.locator('[data-testid=verifactu-grant-form]')).toHaveCount(0);
  await grant.locator('[data-testid=verifactu-grant-resend]').click();
  await expect(grant.locator('[data-testid=verifactu-grant-resend-hint]')).toHaveText(
    'Si algo salió mal, envíalo de nuevo: el envío nuevo sustituye al que está en revisión.',
  );
  await expect(grant.locator('[data-testid=verifactu-grant-form]')).toBeVisible();
  await flowShots(page, 'F06', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-grant-resend-hint]')).toBeVisible();
  });
  await grant.locator('[data-testid=verifactu-grant-resend-cancel]').click();
  await expect(grant.locator('[data-testid=verifactu-grant-form]')).toHaveCount(0);
  await context.close();
});

test('VERIFACTU-F04: «Usar mi propio certificado» chooses who files, the own certificate once loaded', async ({ browser }) => {
  await pushPhoto('none');
  const p12 = join(DIR, 'negocio-f04.p12');
  makeP12(p12);
  const { context, page } = await spanishPage(browser, '/verifactu/config');
  const own = shown(page).locator('[data-testid=verifactu-config-own]');
  await shown(page).locator('[data-testid=verifactu-config-tab-own]').click();
  await own.locator('[data-testid=verifactu-config-cert-file]').setInputFiles(p12);
  await own.locator('[data-testid=verifactu-config-cert-password] input').fill(PASSWORD);
  await own.locator('[data-testid=verifactu-config-cert-upload]').click();
  await expect(own.locator('[data-testid=verifactu-config-cert]')).toContainText('Cargado');

  await page.goto(`${A}/verifactu/settings`);
  const toggle = shown(page).locator('[data-testid=verifactu-settings-own]');
  await toggle.click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Listo: a partir de ahora envías con tu propio certificado.' })).toBeVisible();
  expect(psql('select route from verifactu_config')).toBe('own');
  await flowShots(page, 'F04', async (p) => {
    await expect(shown(p).locator('[data-testid=verifactu-settings-route-hint]')).toBeVisible();
  });
  await toggle.click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Listo: a partir de ahora remite ERPlora en tu nombre.' })).toBeVisible();
  expect(psql('select route from verifactu_config')).toBe('erplora');
  await context.close();
});
