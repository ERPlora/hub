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
 */
const COVERED: Record<string, { prefix: string; contract: string[] }> = {
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
  },
  'components/RepresentationGrantPanel.vue': {
    prefix: 'grant-',
    contract: [
      'grant-document-type',
      'grant-download-model',
      'grant-error',
      'grant-intro',
      'grant-obligado-municipio',
      'grant-obligado-name',
      'grant-obligado-nif',
      'grant-obligado-numero',
      'grant-obligado-via',
      'grant-open-dashboard',
      'grant-party-obligado',
      'grant-party-signer',
      'grant-privacy',
      'grant-rejected-reason',
      'grant-saved-path',
      'grant-signer-municipio',
      'grant-signer-name',
      'grant-signer-nif',
      'grant-signer-numero',
      'grant-signer-via',
      'grant-submit',
    ],
  },
  'components/ResetPanel.vue': {
    prefix: 'reset-',
    contract: ['reset-export-first', 'reset-report', 'reset-submit'],
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
  'views/EmployeesPage.vue': 'hub#PENDING-employees-list',
  'views/ApiKeysPanel.vue': 'hub#PENDING-employees-list',
  'views/LoginPage.vue': 'hub#PENDING-login',
  'views/ProfilePage.vue': 'hub#PENDING-settings',
  'views/SettingsPage.vue': 'hub#PENDING-settings',
  'components/PinPolicyCard.vue': 'hub#PENDING-settings',
  'components/DevicesCard.vue': 'hub#PENDING-settings',
  'components/DeviceModeCard.vue': 'hub#PENDING-settings',
  'components/AssistantDrawer.vue': 'hub#PENDING-assistant',
  'components/ModuleSettingsForm.vue': 'hub#PENDING-assistant',
};

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
      .filter((name) => /from\s+['"][^'"]*\bparked\//.test(readFileSync(join(SRC, name), 'utf8')));
    expect(importers, 'si una pantalla viva lo usa, ya no está aparcado: sácalo de parked/').toEqual(
      [],
    );
  });

  it('la lista de pendientes no nombra pantallas que ya no existen', () => {
    const ghosts = Object.keys(NOT_YET_COVERED).filter(
      (name) => !SURFACES.some((s) => s.name === name),
    );
    expect(ghosts).toEqual([]);
  });
});
