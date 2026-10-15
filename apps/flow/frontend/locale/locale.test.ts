// The flow app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screens showed (the old module's `locales/*.json`) are kept.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from './en.json';
import es from './es.json';

type Catalogue = { [key: string]: string | Catalogue };

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..');

function flatten(catalogue: Catalogue, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(catalogue)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out.set(path, value);
    else for (const [k, v] of flatten(value, path)) out.set(k, v);
  }
  return out;
}

function placeholders(message: string): string[] {
  return [...new Set([...message.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort();
}

/** The app's sources that may name a key: pages, components, composables and helpers (no tests). */
function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.(vue|ts)$/.test(entry.name) && !/\.(test|d)\.ts$/.test(entry.name) ? [path] : [];
  });
}

const EN = flatten(en as unknown as Catalogue);
const ES = flatten(es as unknown as Catalogue);

describe('flow catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['flow']);
    expect(Object.keys(es)).toEqual(['flow']);
  });

  it('have exactly the same keys', () => {
    expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort());
  });

  it('have no empty message', () => {
    for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
  });

  it('keep the same placeholders and plural forms in both languages', () => {
    for (const [key, message] of EN) {
      const spanish = ES.get(key) ?? '';
      expect(placeholders(spanish), key).toEqual(placeholders(message));
      expect(spanish.split('|').length, key).toBe(message.split('|').length);
    }
  });

  it('never use the characters vue-i18n reads as syntax (@ links, {{ }}) by accident', () => {
    for (const [key, message] of [...EN, ...ES]) {
      expect(message, key).not.toMatch(/@|\{\{/);
    }
  });

  it('cover every key the app’s sources use, literal or built from a known prefix', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\bt\(\s*'(flow\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(flow\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every run status, trigger, step, operator and test outcome the server knows', () => {
    for (const status of ['running', 'waiting', 'succeeded', 'stopped', 'failed', 'cancelled']) expect(EN.has(`flow.history.statuses.${status}`), status).toBe(true);
    for (const kind of ['event', 'schedule', 'at', 'manual']) expect(EN.has(`flow.trigger.kinds.${kind}`), kind).toBe(true);
    for (const kind of ['command', 'query', 'condition', 'delay']) expect(EN.has(`flow.steps.add.${kind}`), kind).toBe(true);
    for (const op of ['eq', 'neq', 'in', 'exists', 'contains', 'gt', 'gte', 'lt', 'lte']) expect(EN.has(`flow.steps.operators.${op}`), op).toBe(true);
    for (const outcome of ['high_risk', 'would_run', 'stops_here', 'cannot_tell', 'waits', 'refused', 'not_allowed', 'unavailable', 'not_reached']) {
      expect(EN.has(`flow.test.outcomes.${outcome}`), outcome).toBe(true);
    }
    for (const outcome of ['done', 'found', 'not_found', 'passed', 'stopped', 'waiting', 'waited', 'failed']) expect(EN.has(`flow.history.log.${outcome}`), outcome).toBe(true);
  });

  it('keep the old screens’ words: list, editor, tabs, steps, permissions, gallery', () => {
    const words: Array<[string, string, string]> = [
      ['flow.title', 'Automations', 'Automatizaciones'],
      ['flow.list.new', 'New automation', 'Nueva automatización'],
      ['flow.list.heading', 'Your automations', 'Tus automatizaciones'],
      ['flow.list.search', 'Search by name, by what starts it or by what it does', 'Busca por nombre, por lo que la arranca o por lo que hace'],
      ['flow.list.count', 'Showing {shown} of {total}', 'Se ven {shown} de {total}'],
      ['flow.list.noMatch', 'Nothing here matches that.', 'Aquí no hay nada que encaje con eso.'],
      ['flow.list.clear', 'Show them all again', 'Volver a verlas todas'],
      ['flow.list.bulkEnable', 'Turn them on', 'Encenderlas'],
      ['flow.list.bulkPause', 'Pause them', 'Ponerlas en pausa'],
      ['flow.list.duplicate', 'Make a copy', 'Hacer una copia'],
      ['flow.list.deleteYes', 'Yes, delete it', 'Sí, bórrala'],
      ['flow.list.deleteNo', 'Leave it', 'Déjala'],
      ['flow.active', 'Active', 'Activa'],
      ['flow.paused', 'Paused', 'En pausa'],
      ['flow.unnamed', 'Untitled automation', 'Automatización sin nombre'],
      ['flow.steps.add.command', 'Do something', 'Hacer algo'],
      ['flow.steps.add.query', 'Look something up', 'Consultar algo'],
      ['flow.steps.add.condition', 'Only continue if…', 'Solo sigue si…'],
      ['flow.steps.add.delay', 'Wait', 'Esperar'],
      ['flow.steps.none', 'No steps yet. Add the first thing this automation should do.', 'Todavía no hay pasos. Añade lo primero que debe hacer esta automatización.'],
      ['flow.trigger.when', 'When this happens…', 'Cuando pase esto…'],
      ['flow.editor.tabs.steps', 'Steps', 'Pasos'],
      ['flow.editor.tabs.test', 'Try it', 'Probar'],
      ['flow.editor.tabs.permissions', 'Permissions', 'Permisos'],
      ['flow.editor.tabs.history', 'History', 'Historial'],
      ['flow.editor.save', 'Save', 'Guardar'],
      ['flow.editor.saving', 'Saving…', 'Guardando…'],
      ['flow.permissions.grantAll', 'Allow everything it needs', 'Autorizar todo lo que necesita'],
      ['flow.permissions.missing', 'Waiting for your permission', 'Pendiente de tu permiso'],
      ['flow.permissions.granted', 'Allowed', 'Autorizado'],
      ['flow.history.empty', 'It has not run yet.', 'Todavía no se ha ejecutado.'],
      ['flow.gallery.use', 'Use this one', 'Usar esta'],
      ['flow.gallery.guide', 'How does this work?', '¿Cómo funciona esto?'],
      ['flow.drafts.heading', 'Proposed by the assistant', 'Propuestas por el asistente'],
      ['flow.drafts.badge', 'Draft', 'Borrador'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
