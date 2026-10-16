// The WhatsApp inbox's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON (as the demo's). This test is their guardrail:
// same keys and placeholders in both languages, nothing empty, every key a page, a component or a
// helper of the app uses exists, and the texts the old screens showed are kept word for word.
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

const EN = flatten(en as Catalogue);
const ES = flatten(es as Catalogue);

describe('whatsapp_inbox catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['whatsapp_inbox']);
    expect(Object.keys(es)).toEqual(['whatsapp_inbox']);
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

  it('cover every key the app’s sources use, literal or built from a known prefix', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\bt\(\s*'(whatsapp_inbox\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      // `t(`whatsapp_inbox.status.${status}`)`: the prefix must hold keys.
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(whatsapp_inbox\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every status, delivery status, template category and state the server knows', () => {
    for (const status of ['open', 'pending', 'closed']) expect(EN.has(`whatsapp_inbox.status.${status}`), status).toBe(true);
    for (const status of ['received', 'sent', 'delivered', 'read', 'failed']) {
      expect(EN.has(`whatsapp_inbox.thread.messageStatus.${status}`), status).toBe(true);
    }
    for (const category of ['UTILITY', 'MARKETING', 'AUTHENTICATION']) {
      expect(EN.has(`whatsapp_inbox.templates.categories.${category}`), category).toBe(true);
    }
    for (const state of ['APPROVED', 'PENDING', 'REJECTED', 'PAUSED', 'DISABLED', 'DELETED']) {
      expect(EN.has(`whatsapp_inbox.templates.statuses.${state}`), state).toBe(true);
    }
    for (const blocked of ['not_connected', 'cap_reached', 'unconfigured']) {
      expect(EN.has(`whatsapp_inbox.composer.blocked.${blocked}`), blocked).toBe(true);
    }
  });

  it('keep the old screens’ words (the WORKBOOK’s screens)', () => {
    expect(ES.get('whatsapp_inbox.title')).toBe('Bandeja de WhatsApp');
    expect(ES.get('whatsapp_inbox.settingsTitle')).toBe('Ajustes del canal');
    expect(ES.get('whatsapp_inbox.inbox.search')).toBe('Filtrar contacto o teléfono…');
    expect(ES.get('whatsapp_inbox.inbox.empty')).toBe('Sin conversaciones.');
    expect(ES.get('whatsapp_inbox.inbox.erased')).toBe('Se han borrado los datos de este número.');
    expect(ES.get('whatsapp_inbox.conversation.erase')).toBe('Borrar datos de este número');
    expect(ES.get('whatsapp_inbox.conversation.eraseTitle')).toBe('¿Borrar los datos de este número?');
    expect(ES.get('whatsapp_inbox.conversation.eraseConfirm')).toBe('Borrar datos');
    expect(ES.get('whatsapp_inbox.conversation.loadError')).toBe('No se pudo cargar la conversación');
    expect(ES.get('whatsapp_inbox.templates.empty')).toBe('Sin plantillas.');
    expect(ES.get('whatsapp_inbox.settings.number')).toBe('Tu número');
    expect(ES.get('whatsapp_inbox.settings.templatesTitle')).toBe('Plantillas de Meta');
  });
});
