// Un formulario que el robot de QA no sabe nombrar es un formulario que no prueba nadie (hub#1756).
//
// El QA visual del hub conduce la pantalla con Playwright, y Playwright direcciona por
// `data-testid`: es el único gancho que sobrevive a un cambio de copy, a la traducción `en`↔`es` y
// al Shadow DOM de los Web Components. Cuando un formulario no lo lleva, el QA cae en selectores
// por texto o por `nth` — que es como 80 puntos de CRUD del checklist de restaurante se quedaron
// sin verificar.
//
// Esta es la guardia del PATRÓN, no un parche sobre una pantalla. Cubre tres cosas distintas y por
// eso son tres reglas, no una:
//
//   · COBERTURA — en una superficie registrada, ningún control de formulario se queda sin gancho.
//     Es lo que hace que el campo que alguien añada el mes que viene nazca ya direccionable.
//   · CONTRATO — los nombres que el QA escribe en sus specs están declarados aquí, y el conjunto
//     declarado es EXACTAMENTE el que hay en el fichero. Un `data-testid` es un contrato con quien
//     lo usa desde fuera: renombrarlo en silencio rompe la suite de QA en otro repo, así que
//     renombrarlo tiene que romper ESTE test primero, aquí, donde se ve.
//   · TRINQUETE — toda pantalla con formulario está clasificada: o cubierta, o en la lista de
//     pendientes con su issue. Una `.vue` nueva con un `ion-input` no puede colarse sin decidirlo,
//     y una que ya esté cubierta no puede quedarse fuera de la lista de cubiertas.
//
// La convención está escrita en `architecture/hub/apps/testids.md`. En una línea:
// `<superficie>-<campo|acción|estado>`, kebab-case, y las filas de una lista llevan su identidad
// al final (`import-module-${id}`).
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('.', import.meta.url));

/**
 * Superficie cubierta: `prefix` es el espacio de nombres que le pertenece y `contract` es el
 * conjunto EXACTO de `data-testid` literales que el fichero declara hoy.
 *
 * Para entrar aquí una pantalla necesita las dos mitades: todo control con gancho (regla de
 * cobertura) y su contrato escrito (regla de contrato). Añadir un campo a una de estas pantallas
 * obliga a tocar esta lista — a propósito: es el momento en el que alguien decide cómo se va a
 * llamar ese campo para el resto del mundo.
 *
 * `computed` is that same contract for the hooks Vue builds at render time (`:data-testid`),
 * declared by their FIXED part — the head QA can predict, with the row's identity appended. They
 * used to be invisible here: renaming one stayed green and broke the specs addressing it (hub#1828).
 */
const COVERED: Record<string, { prefix: string; contract: string[]; computed?: string[] }> = {
  // La pantalla de esta issue: alta, edición y baja de una persona del hub (`/employees/new` y
  // `/employees/:id`). Es la ruta por la que el QA puede montar la plantilla entera —y con ella la
  // matriz de roles del checklist— sin tocar un solo selector por texto.
  'views/EmployeeFormPage.vue': {
    prefix: 'employee-',
    contract: [
      'employee-active',
      'employee-badge',
      'employee-cancel',
      'employee-clear-badge',
      'employee-clear-pin',
      'employee-email',
      'employee-error',
      'employee-form',
      'employee-load-error',
      'employee-loading',
      'employee-local',
      'employee-name',
      'employee-pin',
      'employee-retry',
      'employee-role',
      'employee-submit',
    ],
  },
  // Regression test for ERPlora/hub#1808 — the staff list and the API keys panel.
  // The staff list (`/employees`): the tabs, the table and the quick-add form that lives in the
  // side panel. `employees-` and not `employee-` on purpose — the singular is one person's form,
  // and they are two different screens the QA walks through one after the other.
  'views/EmployeesPage.vue': {
    prefix: 'employees-',
    contract: [
      'employees-email',
      'employees-form',
      'employees-form-error',
      'employees-load-error',
      'employees-loading',
      'employees-local',
      'employees-name',
      'employees-pin',
      'employees-retry',
      'employees-role',
      'employees-submit',
      'employees-tab-apikeys',
      'employees-tab-approvals',
      'employees-tab-roles',
      'employees-tab-staff',
      'employees-table',
      'employees-tabs',
    ],
  },
  // Machine API keys (the «API keys» tab of the staff list). The modules × {read, write} matrix
  // is named COMPUTED by module id, like the import rows: by index, one extra installed module
  // would move the assertion to another row.
  'views/ApiKeysPanel.vue': {
    prefix: 'api-key-',
    contract: [
      'api-key-access',
      'api-key-all-read',
      'api-key-all-write',
      'api-key-cancel',
      'api-key-create',
      'api-key-create-close',
      'api-key-create-modal',
      'api-key-modules-loading',
      'api-key-name',
      'api-key-no-modules',
      'api-key-rate-limit',
      'api-key-secret',
      'api-key-secret-close',
      'api-key-secret-copy',
      'api-key-secret-done',
      'api-key-secret-modal',
      'api-key-table',
    ],
    computed: [
      'api-key-read-',
      'api-key-write-',
    ],
  },
  // El flujo de import de blueprints es el patrón de referencia citado por hub#1756: ya era el
  // único que el QA sabía conducir. Queda congelado aquí para que siga siéndolo.
  'components/ImportPanel.vue': {
    prefix: 'import-',
    contract: [
      'import-blueprint-table',
      'import-catalog-retry',
      'import-cloud-loading',
      'import-done',
      'import-error',
      'import-file-input',
      'import-lead',
      'import-manifest',
      'import-report',
      'import-report-dismiss',
      'import-report-recovered',
      'import-report-retry',
      'import-retry-error',
      'import-retry-reason',
      'import-section-fiscal',
      'import-section-media',
      'import-section-settings',
      'import-section-users',
      'import-submit',
      'import-upload-local',
    ],
    computed: [
      'import-module-',
    ],
  },
  // Regression test for ERPlora/hub#1809 — the hub's front door.
  // The hub's front door (`/login` and `/auth/google/callback`): the four steps —email+password,
  // 2FA by email, PIN and PIN setup— live on the same screen, so the name carries the step
  // (`login-2fa-code`, `login-setup-pinpad`). Without these hooks no journey could enter through
  // the real door: the session was injected by API and the login itself went untested.
  'views/LoginPage.vue': {
    prefix: 'login-',
    contract: [
      'login-2fa-back',
      'login-2fa-code',
      'login-2fa-error',
      'login-2fa-form',
      'login-2fa-submit',
      'login-box',
      'login-choose-user',
      'login-choose-user-to-email',
      'login-email',
      'login-email-form',
      'login-error',
      'login-google',
      'login-password',
      'login-pin-error',
      'login-pin-step',
      'login-pin-to-email',
      'login-pinpad',
      'login-session-ended',
      'login-setup-error',
      'login-setup-pinpad',
      'login-setup-step',
      'login-submit',
      'login-tab-email',
      'login-tab-pin',
      'login-tabs',
      'login-theme',
      'login-trust',
      'login-trust-info',
      'login-upgrade-plan',
      'login-use-pin',
    ],
    computed: [
      'login-pin-user-',
    ],
  },
  // Regression test for ERPlora/hub#1810 — profile, hub settings, PIN policy, devices and
  // device mode.
  // The account of whoever uses the hub (`/profile`): identity, language, appearance and own PIN.
  'views/ProfilePage.vue': {
    prefix: 'profile-',
    contract: [
      'profile-avatar-input',
      'profile-change-photo',
      'profile-confirm-pin',
      'profile-current-pin',
      'profile-email',
      'profile-first-name',
      'profile-language',
      'profile-last-name',
      'profile-manage-account',
      'profile-new-pin',
      'profile-pin-form',
      'profile-remove-photo',
      'profile-save',
      'profile-save-pin',
      'profile-theme',
      'profile-use-hub-appearance',
    ],
  },
  // The hub settings (`/settings`), with their five tabs. This is where who gets in and with what
  // is decided, so it is the most expensive surface to leave undriven: the business country and
  // currency, the fiscal identity, the certificate and each app's permissions.
  //
  // The three hooks of the fiscal route were called `fiscal-route-*` and become
  // `settings-fiscal-route-*`: the screen prefix is mandatory (`architecture/hub/apps/testids.md`)
  // and without it two screens can coin the same name. Their only consumer
  // —`views/settings-fiscal-route.test.ts`— changes in this same commit, which is exactly what the
  // contract rule asks for: a rename breaks here, not the QA suite three days later.
  'views/SettingsPage.vue': {
    prefix: 'settings-',
    contract: [
      'settings-api-docs',
      'settings-autostart',
      'settings-business-address-legacy',
      'settings-business-city',
      'settings-business-postal-code',
      'settings-business-street',
      'settings-business-street-number',
      'settings-business-legal-name',
      'settings-business-tax-id',
      'settings-country',
      'settings-currency',
      'settings-hardware',
      'settings-hub-language',
      'settings-hub-palette',
      'settings-permissions-empty',
      'settings-permissions-loading',
      'settings-print-coverage-error',
      'settings-receipt-template',
      'settings-save-business',
      'settings-share-with-erplora',
      'settings-tab-data',
      'settings-tab-hub',
      'settings-tab-permissions',
      'settings-tab-business',
      'settings-tab-tickets',
      'settings-tabs',
      'settings-timezone',
    ],
    computed: [
      'settings-capability-',
      'settings-capability-breaks-',
    ],
  },
  // «Ask who is selling» (Settings › Hub): the pinpad toggle, the idle dial and the PIN length.
  // It is the card the PIN e2e depends on.
  'components/PinPolicyCard.vue': {
    prefix: 'pin-policy-',
    contract: [
      'pin-policy-admin-only',
      'pin-policy-card',
      'pin-policy-error',
      'pin-policy-idle',
      'pin-policy-length',
      // hub#1794: the title of the digits row, now on its own line above the choice.
      'pin-policy-length-title',
      'pin-policy-pinpad',
    ],
  },
  // The device inventory («I lost the tablet»). Each row carries its `deviceId` at the end,
  // computed: by index, revoking would point at another tablet as soon as a new one came in.
  //
  // The rows carried `data-test` —without `id`—, which neither Playwright resolves with
  // `getByTestId` nor the guard sees. They become `data-testid` with the card prefix, and
  // `DevicesCard.test.ts` moves with them, in this same commit.
  'components/DevicesCard.vue': {
    prefix: 'devices-',
    contract: ['devices-admin-only', 'devices-card', 'devices-empty', 'devices-error'],
    computed: [
      'devices-cancel-',
      'devices-cancel-name-',
      'devices-confirm-',
      'devices-name-',
      'devices-rename-',
      'devices-revoke-',
      'devices-save-name-',
    ],
  },
  // «This device» (Settings › Hub): shared or personal, the decision of whether this till asks for a PIN.
  'components/DeviceModeCard.vue': {
    prefix: 'device-mode-',
    contract: [
      'device-mode-admin-only',
      'device-mode-card',
      'device-mode-error',
      'device-mode-options',
      'device-mode-personal',
      'device-mode-shared',
    ],
  },
  // Las cinco de abajo ya estaban completas antes de hub#1756 (medido: ningún control sin gancho).
  // Entran para que no se deshagan solas: el contrato de elevación/export/otorgamiento/reset lo usa
  // hoy la suite e2e del shell.
  'components/ElevationDialog.vue': {
    prefix: 'elevation-',
    contract: [
      'elevation-badge-hint',
      'elevation-cancel',
      'elevation-continue',
      'elevation-error',
      'elevation-lead',
      'elevation-modal',
      'elevation-name',
      'elevation-person',
      'elevation-pinpad',
      'elevation-what',
    ],
  },
  'components/ExportPanel.vue': {
    prefix: 'export-',
    contract: [
      'export-error',
      'export-fiscal-note',
      'export-lead',
      'export-locale',
      'export-modules-table',
      'export-name',
      'export-purpose',
      'export-purpose-locked',
      'export-section-fiscal',
      'export-section-media',
      'export-section-settings',
      'export-section-users',
      'export-select-all',
      'export-submit',
    ],
    computed: [
      'export-table-',
    ],
  },
  'components/ResetPanel.vue': {
    prefix: 'reset-',
    contract: ['reset-export-first', 'reset-report', 'reset-submit'],
    computed: [
      'reset-batch-',
      'reset-section-',
      'reset-undo-',
    ],
  },
  'components/UserSwitchOverlay.vue': {
    prefix: 'user-switch-',
    contract: [
      'user-switch-cancel',
      'user-switch-continue',
      'user-switch-error',
      'user-switch-lead',
      'user-switch-modal',
      'user-switch-name',
      'user-switch-person',
      'user-switch-pinpad',
    ],
  },
  // Regression test for ERPlora/hub#1811 — the assistant drawer and a module's settings form.
  // The shell's ✨ drawer. Thread messages are named COMPUTED by their turn
  // (`assistant-message-${i}`): a chat thread only APPENDS —nothing is reordered or inserted in
  // the middle—, so the turn IS the row identity, and it is what a spec needs to read «the last
  // answer». Same for the grounding line and the «typing» spinner, which live inside the same
  // `v-for`.
  'components/AssistantDrawer.vue': {
    prefix: 'assistant-',
    contract: [
      'assistant-attach',
      'assistant-attach-error',
      'assistant-attach-input',
      'assistant-close',
      'assistant-drawer',
      'assistant-empty',
      'assistant-input',
      'assistant-mic',
      'assistant-quota-ask-admin',
      'assistant-quota-cta',
      'assistant-quota-managed-in-account',
      'assistant-quota-warning',
      'assistant-report',
      'assistant-send',
      'assistant-stop',
      'assistant-suggest-missing',
      'assistant-thread',
      'assistant-voice-error',
    ],
    computed: [
      'assistant-goto-',
      'assistant-grounding-',
      'assistant-message-',
      'assistant-suggest-',
      'assistant-typing-',
    ],
  },
  // An app's settings. The form is GENERATED from the module manifest, so the hook cannot be a
  // literal per field: it derives from the setting key (`module-settings-field-${key}`), like the
  // import rows. The four control branches —toggle, select, number, text— are mutually exclusive,
  // so they share the name: the spec asks for the setting by its key and does not need to know
  // which control the shell painted it with.
  'components/ModuleSettingsForm.vue': {
    prefix: 'module-settings-',
    contract: [
      'module-settings-admin-only',
      'module-settings-error',
      'module-settings-loading',
      'module-settings-refusal',
      'module-settings-save',
    ],
    computed: [
      'module-settings-field-',
      'module-settings-invalid-',
      'module-settings-preview-',
    ],
  },
  // Control reutilizable: el `data-testid` se lo pone QUIEN lo usa (`:data-testid="testid"`), así
  // que no tiene nombres propios que congelar. El botón es el disfraz del input y no lleva gancho
  // a propósito — lo que un e2e rellena es el `<input type="file">`.
  'components/GrantFilePicker.vue': { prefix: '', contract: [] },
};

/**
 * Pantallas con formulario que todavía no llevan ganchos, cada una con la issue que lo pide.
 *
 * La lista solo puede ENCOGER: cuando una se completa sale de aquí y entra arriba (el test de
 * entrada obsoleta falla si se queda). Una `.vue` nueva no nace en esta lista — nace cubierta.
 */
const NOT_YET_COVERED: Record<string, string> = {
};

/**
 * Cuántas pantallas hay en la lista de pendientes HOY. Este número SOLO BAJA: cuando una pantalla
 * pasa a `COVERED` se resta uno, y nunca se suma. Sin él, la lista de pendientes era una lista de
 * excepciones: una `.vue` nueva con formulario entraba en `NOT_YET_COVERED` con una issue de adorno
 * (`hub#999999`) y la guardia seguía en verde — medido como mutante al revisar hub#1813. Con el
 * número clavado, meter una pantalla nueva en pendientes obliga a subirlo a mano, en una línea cuyo
 * comentario dice que no se sube.
 */
const PENDING_TODAY = 0;

/** Lo que una persona rellena. No son botones: los botones se declaran en el contrato. */
const CONTROL_TAGS = [
  'ion-input',
  'ion-select',
  'ion-textarea',
  'ion-toggle',
  'ion-checkbox',
  'ion-searchbar',
  'ion-radio-group',
  'ion-datetime',
  'ion-range',
  'input',
  'select',
  'textarea',
] as const;

const CONTROL_OPEN = new RegExp(`<(${CONTROL_TAGS.join('|')})(?=[\\s/>])`, 'g');

/** `data-testid="…"` escrito a mano. El `:data-testid` de Vue (valor calculado) NO cuenta aquí. */
const LITERAL_TESTID = /(?<![:\w-])data-testid="([^"]*)"/g;

/**
 * The other half: the hook whose name Vue builds at render time, `:data-testid` with a template.
 * QA addresses it as «fixed head + the row's identity», so the head is the contract — and the
 * literal rules above never see it, on purpose (`LITERAL_TESTID` excludes `:data-testid`). That
 * blind spot is hub#1828: renaming `login-pin-user-` left this file at 11/11 green while the specs
 * that clicked it broke somewhere else, days later and in another repo.
 */
const COMPUTED_TESTID = /(?<![\w-]):data-testid="([^"]*)"/g;

/**
 * Any `data-test…` attribute, so the guard can tell the hook from the variants that look like one
 * and are not. Playwright resolves `getByTestId` against `data-testid` and nothing else
 * (`testIdAttribute` is not overridden in `tests/playwright.config.ts`), so `data-test="x"` is a
 * hook the robot cannot reach — and the spec that reads it asserts on nothing for ever.
 */
const TEST_ATTR = /(?<![\w-])(data-test[\w-]*)\s*=\s*("[^"]*"|'[^']*')?/g;

/**
 * How a hook is WRITTEN. Every rule above reads exactly two spellings — `data-testid="…"` and
 * `:data-testid="…"` — so any other way of writing the SAME attribute is a hook Vue renders, QA
 * can address, and this file never sees. Measured on this branch: a brand-new computed hook spelled
 * `v-bind:data-testid` (the longhand `:` is short for) left the guard at 16/16 green, and so did a
 * single-quoted value. Both are the hole hub#1828 exists to close, written a different way.
 *
 * Teaching four regexes three spellings each would be four places to forget one. The shell writes
 * ONE form and this rule says so: a guard that reads a single spelling has to forbid the rest, or
 * it fails open on the next person who types the longhand.
 */
const TESTID_SPELLING = /(?<![\w-])(v-bind:data-testid|:?data-testid)\s*=\s*("|'|[^\s"'>])/g;

/** Kebab-case: minúsculas y dígitos separados por un solo guión. */
const KEBAB = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;

/** El `>` que cierra la etiqueta de apertura, saltándose los `>` que viven dentro de comillas. */
function openTag(source: string, start: number): string {
  let quote: string | null = null;
  for (let i = start; i < source.length; i++) {
    const c = source[i];
    if (quote) {
      if (c === quote) quote = null;
    } else if (c === '"' || c === "'") quote = c;
    else if (c === '>') return source.slice(start, i + 1);
  }
  return source.slice(start);
}

/**
 * `src/parked/` queda fuera del barrido: es markup de referencia que no enruta nadie, así que no
 * tiene contrato con el QA — no hay pantalla que abrir. La exclusión no es un agujero porque el
 * último test de este fichero comprueba que sigue siendo cierta: si algo vivo importa de `parked/`,
 * deja de ser código aparcado y vuelve al barrido.
 */
const PARKED = 'parked';

/**
 * Una referencia de módulo a `parked/`, en las cuatro formas en las que se escribe una: `from`,
 * `import(...)` en diferido, `import` a secas y `require`.
 *
 * Mirar solo `from` dejaba pasar justo la forma REALISTA, y con ella la única manera en que una
 * pantalla aparcada vuelve a la vida: las rutas del shell son todas
 * `component: () => import('../views/X.vue')` (`router/index.ts`), así que enrutar una pantalla de
 * `parked/` no escribe ningún `from` — y la guardia se quedaba verde con la pantalla ya servida a
 * los usuarios y sin un solo gancho. Medido como mutante al re-verificar hub#1756.
 */
const PARKED_IMPORT = /(?:\bfrom|\bimport|\brequire)\s*\(?\s*['"][^'"]*\bparked\//;

function vueFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== PARKED) vueFiles(full, found);
    } else if (entry.endsWith('.vue')) found.push(full);
  }
  return found;
}

/** Todo fichero de `src/`, para comprobar quién importa de `parked/`. */
function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (/\.(ts|vue|mts)$/.test(entry)) found.push(full);
  }
  return found;
}

/** Todas las `.vue` del shell, con la ruta relativa a `src/` que usan los registros de arriba. */
const SURFACES: Array<{ name: string; source: string }> = vueFiles(SRC)
  .map((full) => ({ name: relative(SRC, full), source: readFileSync(full, 'utf8') }))
  .sort((a, b) => a.name.localeCompare(b.name));

/** The Playwright tree: the other half of the shell for the attribute rule below. */
const TESTS = fileURLToPath(new URL('../tests/', import.meta.url));

/**
 * Everything the shell is made of AND every spec that drives it — `src/` (`parked/` included: an
 * unreachable hook is worth nothing there either) plus `tests/`.
 *
 * The attribute rule has to reach both halves. A screen that writes `data-test` is a screen the
 * robot cannot address; a spec that keeps reading `[data-test="…"]` after the screen stopped
 * writing it asserts `exists() === false` for ever, which is how a rule that never fires disguises
 * itself as a rule that passes.
 *
 * This very file is the only exclusion, and it has to be: a guard that forbids an attribute has to
 * spell the attribute out in order to forbid it.
 */
const SHELL_SOURCES: Array<{ name: string; source: string }> = [
  ...sourceFiles(SRC).map((full) => ({ root: SRC, full })),
  ...sourceFiles(TESTS).map((full) => ({ root: TESTS, full })),
]
  .map(({ root, full }) => ({
    name: (root === SRC ? '' : '../tests/') + relative(root, full),
    source: readFileSync(full, 'utf8'),
  }))
  .filter(({ name }) => !name.endsWith('form-testids.test.ts'))
  .sort((a, b) => a.name.localeCompare(b.name));

const templateOf = (source: string): string =>
  source.match(/<template>([\s\S]*)<\/template>/)?.[1] ?? '';

/** Controles de formulario de una superficie, con el texto de su etiqueta de apertura. */
function controls(source: string): Array<{ tag: string; line: number; open: string }> {
  const template = templateOf(source);
  const found: Array<{ tag: string; line: number; open: string }> = [];
  CONTROL_OPEN.lastIndex = 0;
  for (let m = CONTROL_OPEN.exec(template); m; m = CONTROL_OPEN.exec(template)) {
    found.push({
      tag: m[1],
      line: template.slice(0, m.index).split('\n').length,
      open: openTag(template, m.index),
    });
  }
  return found;
}

/** Lleva gancho, sea literal (`data-testid="x"`) o calculado (`:data-testid="…"`). */
const hasTestid = (openTagText: string): boolean => /(?:^|\s):?data-testid\s*=/.test(openTagText);

function literalTestids(source: string): string[] {
  const found: string[] = [];
  LITERAL_TESTID.lastIndex = 0;
  for (let m = LITERAL_TESTID.exec(source); m; m = LITERAL_TESTID.exec(source)) found.push(m[1]);
  return found;
}

/**
 * The fixed head of a computed hook: a template `devices-rename-` + the interpolated id → the
 * string `devices-rename-`.
 *
 * `null` means the expression spells out no predictable head, and there are exactly two ways to
 * write one: a bare prop (`:data-testid="testid"` — the reusable control, whose HOST writes the
 * name) or a template that opens with the interpolation. The first is legal on a control with no
 * namespace of its own; the second is addressable by nobody, and the rules below say so.
 */
function fixedPartOf(expression: string): string | null {
  const template = expression.match(/^`([^`]*)`$/);
  if (!template) return null;
  const head = template[1].split('${')[0];
  return head === '' ? null : head;
}

function computedTestids(source: string): Array<{ expression: string; fixed: string | null }> {
  const found: Array<{ expression: string; fixed: string | null }> = [];
  COMPUTED_TESTID.lastIndex = 0;
  for (let m = COMPUTED_TESTID.exec(source); m; m = COMPUTED_TESTID.exec(source)) {
    found.push({ expression: m[1], fixed: fixedPartOf(m[1]) });
  }
  return found;
}

/** The fixed heads a screen writes today, deduplicated — every row of a list shares one head. */
const fixedParts = (source: string): string[] => [
  ...new Set(
    computedTestids(source)
      .map((c) => c.fixed)
      .filter((fixed): fixed is string => fixed !== null),
  ),
];

const uncoveredControls = (source: string): string[] =>
  controls(source)
    .filter((c) => !hasTestid(c.open))
    .map((c) => `<${c.tag}> línea ${c.line}`);

describe('data-testid — convención del shell (hub#1756)', () => {
  it('todo data-testid literal es kebab-case', () => {
    const offenders: string[] = [];
    for (const { name, source } of SURFACES) {
      for (const value of literalTestids(source)) {
        if (!KEBAB.test(value)) offenders.push(`${name}: "${value}"`);
      }
    }
    expect(offenders, 'un nombre que no es kebab-case rompe la predicción del QA').toEqual([]);
  });

  it('ningún data-testid literal se repite en dos pantallas', () => {
    const owners = new Map<string, string[]>();
    for (const { name, source } of SURFACES) {
      for (const value of new Set(literalTestids(source))) {
        owners.set(value, [...(owners.get(value) ?? []), name]);
      }
    }
    const shared = [...owners]
      .filter(([, files]) => files.length > 1)
      .map(([value, files]) => `"${value}" en ${files.join(' + ')}`);
    expect(shared, 'getByTestId devolvería dos elementos y el spec elegiría al azar').toEqual([]);
  });

  it('las pantallas cubiertas no dejan ningún control sin gancho', () => {
    const offenders: string[] = [];
    for (const [name, _spec] of Object.entries(COVERED)) {
      const surface = SURFACES.find((s) => s.name === name);
      expect(surface, `${name} está en COVERED pero no existe`).toBeDefined();
      for (const control of uncoveredControls(surface!.source)) offenders.push(`${name}: ${control}`);
    }
    expect(offenders, 'un control sin data-testid no lo puede rellenar Playwright').toEqual([]);
  });

  it('el contrato declarado es EXACTAMENTE el que hay en la pantalla', () => {
    const drift: string[] = [];
    for (const [name, spec] of Object.entries(COVERED)) {
      const surface = SURFACES.find((s) => s.name === name);
      const found = [...new Set(literalTestids(surface?.source ?? ''))].sort();
      const declared = [...spec.contract].sort();
      for (const missing of declared.filter((v) => !found.includes(v))) {
        drift.push(`${name}: el contrato declara "${missing}" y la pantalla ya no lo tiene`);
      }
      for (const extra of found.filter((v) => !declared.includes(v))) {
        drift.push(`${name}: la pantalla tiene "${extra}" y el contrato no lo declara`);
      }
    }
    expect(drift, 'renombrar un data-testid rompe la suite de QA: decláralo aquí').toEqual([]);
  });

  it('the fixed head of every computed hook is kebab-case', () => {
    const offenders: string[] = [];
    for (const { name, source } of SURFACES) {
      for (const fixed of fixedParts(source)) {
        if (!KEBAB.test(fixed.replace(/-$/, ''))) offenders.push(`${name}: "${fixed}"`);
      }
    }
    expect(offenders, 'a head that is not kebab-case breaks what QA predicts').toEqual([]);
  });

  it('the computed contract is EXACTLY the one on the screen', () => {
    const drift: string[] = [];
    for (const [name, spec] of Object.entries(COVERED)) {
      const surface = SURFACES.find((s) => s.name === name);
      const found = fixedParts(surface?.source ?? '').sort();
      const declared = [...(spec.computed ?? [])].sort();
      for (const missing of declared.filter((v) => !found.includes(v))) {
        drift.push(`${name}: the contract declares "${missing}…" and the screen no longer has it`);
      }
      for (const extra of found.filter((v) => !declared.includes(v))) {
        drift.push(`${name}: the screen has "${extra}…" and the contract does not declare it`);
      }
    }
    expect(drift, 'renaming a computed data-testid breaks the QA suite: declare it here').toEqual(
      [],
    );
  });

  it('every computed hook lives in the namespace of its screen', () => {
    const offenders: string[] = [];
    for (const [name, spec] of Object.entries(COVERED)) {
      if (!spec.prefix) continue;
      const surface = SURFACES.find((s) => s.name === name);
      for (const fixed of fixedParts(surface?.source ?? '')) {
        if (!fixed.startsWith(spec.prefix)) offenders.push(`${name}: "${fixed}…" ≠ ${spec.prefix}*`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('a computed hook with no fixed head only belongs to a reusable control', () => {
    // A screen with a namespace of its own spells its hooks out; `prefix: ''` is how this register
    // marks the control that has none, because whoever uses it writes the name (`GrantFilePicker`).
    const offenders: string[] = [];
    for (const [name, spec] of Object.entries(COVERED)) {
      if (!spec.prefix) continue;
      const surface = SURFACES.find((s) => s.name === name);
      for (const { expression, fixed } of computedTestids(surface?.source ?? '')) {
        if (fixed === null) offenders.push(`${name}: :data-testid="${expression}"`);
      }
    }
    expect(
      offenders,
      'QA cannot predict a name the screen does not spell out: give the hook a fixed head',
    ).toEqual([]);
  });

  it('nothing in the shell writes data-test: Playwright only resolves data-testid', () => {
    const offenders: string[] = [];
    for (const { name, source } of SHELL_SOURCES) {
      TEST_ATTR.lastIndex = 0;
      for (let m = TEST_ATTR.exec(source); m; m = TEST_ATTR.exec(source)) {
        if (m[1] !== 'data-testid') offenders.push(`${name}: ${m[1]}=${m[2] ?? ''}`);
      }
    }
    expect(
      offenders,
      'getByTestId does not resolve it: write data-testid, prefixed with its screen',
    ).toEqual([]);
  });

  it('a hook is spelled data-testid="…" or :data-testid="…", and nothing else', () => {
    const offenders: string[] = [];
    for (const { name, source } of SURFACES) {
      TESTID_SPELLING.lastIndex = 0;
      for (let m = TESTID_SPELLING.exec(source); m; m = TESTID_SPELLING.exec(source)) {
        if (m[1] === 'v-bind:data-testid' || m[2] !== '"') offenders.push(`${name}: ${m[1]}=${m[2]}`);
      }
    }
    expect(
      offenders,
      'the rules above read one spelling: any other is a hook with no contract',
    ).toEqual([]);
  });

  it('cada data-testid vive en el espacio de nombres de su pantalla', () => {
    const offenders: string[] = [];
    for (const [name, spec] of Object.entries(COVERED)) {
      if (!spec.prefix) continue;
      const surface = SURFACES.find((s) => s.name === name);
      for (const value of new Set(literalTestids(surface?.source ?? ''))) {
        if (!value.startsWith(spec.prefix)) offenders.push(`${name}: "${value}" ≠ ${spec.prefix}*`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('toda pantalla con formulario está clasificada: cubierta o con su issue', () => {
    const unclassified = SURFACES.filter(
      ({ name, source }) =>
        controls(source).length > 0 && !(name in COVERED) && !(name in NOT_YET_COVERED),
    ).map(({ name }) => name);
    expect(
      unclassified,
      'una pantalla de formulario nueva nace con data-testid — o entra en NOT_YET_COVERED con su issue',
    ).toEqual([]);
  });

  it('una pendiente que ya está completa no se queda en la lista de pendientes', () => {
    const stale = Object.keys(NOT_YET_COVERED).filter((name) => {
      const surface = SURFACES.find((s) => s.name === name);
      return surface !== undefined && uncoveredControls(surface.source).length === 0;
    });
    expect(stale, 'ya tiene todos los ganchos: pásala a COVERED con su contrato').toEqual([]);
  });

  it('nada vivo importa de src/parked/, que es lo que lo deja fuera del barrido', () => {
    const importers = sourceFiles(SRC)
      .map((full) => relative(SRC, full))
      .filter((name) => !name.startsWith(`${PARKED}/`))
      .filter((name) => PARKED_IMPORT.test(readFileSync(join(SRC, name), 'utf8')));
    expect(importers, 'si una pantalla viva lo usa, ya no está aparcado: sácalo de parked/').toEqual(
      [],
    );
  });

  it('la lista de pendientes solo encoge: una pantalla nueva nace cubierta, no pendiente', () => {
    const pending = Object.keys(NOT_YET_COVERED).length;
    expect(
      pending,
      pending > PENDING_TODAY
        ? 'una pantalla nueva no entra en NOT_YET_COVERED: ponle sus data-testid y pásala a COVERED'
        : 'una pendiente salió de la lista: baja PENDING_TODAY a ' + pending,
    ).toBe(PENDING_TODAY);
  });

  it('la lista de pendientes no nombra pantallas que ya no existen', () => {
    const ghosts = Object.keys(NOT_YET_COVERED).filter(
      (name) => !SURFACES.some((s) => s.name === name),
    );
    expect(ghosts).toEqual([]);
  });

  it('cada pendiente cita una issue de verdad, no un hueco', () => {
    // Una pendiente sin issue es una pendiente que no hace nadie: el registro de abajo se lee como
    // un plan, y un `repo#PENDING-algo` lo convierte en una lista de buenas intenciones que nunca
    // entra en el board. Forma exacta `repo#N` para que se pueda abrir desde aquí.
    const placeholders = Object.entries(NOT_YET_COVERED)
      .filter(([, issue]) => !/^[a-z][a-z0-9-]*#\d+$/.test(issue))
      .map(([name, issue]) => `${name}: "${issue}"`);
    expect(placeholders, 'abre la issue y pon su número: el hueco no lo recoge el board').toEqual(
      [],
    );
  });
});
