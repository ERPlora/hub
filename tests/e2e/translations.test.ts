// The translations the master QA of the Hub checks on screen (BASE-G152, base-qa-master.spec.ts): the hub's catalogues
// (`en` source, `es` translation; the SPA's JSON and Django's `.po`) and which visible texts are in the other language or
// are a raw message key.
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { catalogOf, jsonPairs, loadCatalog, normalText, poPairs, rawKeys, wrongLanguage } from './translations';

describe('poPairs', () => {
  it('pairs each msgid with its msgstr, across continuation lines and escapes', () => {
    const po = [
      'msgid ""',
      'msgstr ""',
      '"Content-Type: text/plain; charset=UTF-8\\n"',
      '',
      '#: base/apps.py:10',
      'msgid "Settings"',
      'msgstr "Ajustes"',
      '',
      'msgid ""',
      '"The business is "',
      '"\\"ready\\"."',
      'msgstr ""',
      '"El negocio está "',
      '"\\"listo\\"."',
    ].join('\n');
    expect(poPairs(po)).toEqual([
      ['Settings', 'Ajustes'],
      ['The business is "ready".', 'El negocio está "listo".'],
    ]);
  });

  it('leaves out the header, an untranslated msgid and a fuzzy one', () => {
    const po = ['msgid "Files"', 'msgstr ""', '', '#, fuzzy', 'msgid "System"', 'msgstr "Sistema"'].join('\n');
    expect(poPairs(po)).toEqual([]);
  });

  it('pairs a plural: the singular with msgstr[0], the plural with msgstr[1]', () => {
    const po = ['msgid "%(n)s app"', 'msgid_plural "%(n)s apps"', 'msgstr[0] "%(n)s app"', 'msgstr[1] "%(n)s apps"'].join('\n');
    expect(poPairs(po)).toEqual([
      ['%(n)s app', '%(n)s app'],
      ['%(n)s apps', '%(n)s apps'],
    ]);
  });
});

describe('jsonPairs', () => {
  it('pairs the texts of the same key in both catalogues, nested and in lists', () => {
    const en = { base: { title: 'Home', tabs: ['Summary', 'Activity'], only: 'Not in es' } };
    const es = { base: { title: 'Inicio', tabs: ['Resumen', 'Actividad'] } };
    expect(jsonPairs(en, es)).toEqual([
      ['Home', 'Inicio'],
      ['Summary', 'Resumen'],
      ['Activity', 'Actividad'],
    ]);
  });
});

describe('catalogOf', () => {
  it('keeps the texts of one language only: not those the same in both, with a value or written in the other', () => {
    const catalog = catalogOf([
      ['Settings', 'Ajustes'],
      ['Plan', 'Plan'],
      ['Hello, {name}', 'Hola, {name}'],
      ['%(count)s apps', '%(count)s apps'],
      ['General', 'General'],
      ['Total', 'Importe'],
      ['Amount', 'Total'],
    ]);
    expect([...catalog.en].sort()).toEqual(['Amount', 'Settings']);
    expect([...catalog.es].sort()).toEqual(['Ajustes', 'Importe']);
  });

  it('never a single letter: an initial or a day\'s letter reads the same in both', () => {
    const catalog = catalogOf([
      ['W', 'X'],
      ['Mo', 'Lu'],
    ]);
    expect([...catalog.en]).toEqual(['Mo']);
    expect([...catalog.es]).toEqual(['Lu']);
  });
});

describe('normalText', () => {
  it('collapses spaces, non-breaking ones too, and trims', () => {
    expect(normalText('  Mis apps \n  y más ')).toBe('Mis apps y más');
  });
});

describe('wrongLanguage', () => {
  const catalog = catalogOf([
    ['Settings', 'Ajustes'],
    ['Employees', 'Empleados'],
  ]);

  it('in Spanish, a text that only the English catalogue has', () => {
    expect(wrongLanguage(['Ajustes', ' Employees ', 'Lucía', 'Settings and more'], 'es', catalog)).toEqual(['Employees']);
  });

  it('in English, a text that only the Spanish catalogue has', () => {
    expect(wrongLanguage(['Settings', 'Empleados'], 'en', catalog)).toEqual(['Empleados']);
  });

  it('each text once', () => {
    expect(wrongLanguage(['Employees', 'Employees'], 'es', catalog)).toEqual(['Employees']);
  });
});

describe('rawKeys', () => {
  it('a message key shown as text, never an address, a host or a sentence', () => {
    expect(
      rawKeys([
        'base.apps.add',
        'base.systemPlan.tabs.plan',
        'owner@example.com',
        'qa-1.localhost',
        'erplora.com',
        'v1.2.3',
        'See base.apps.add here',
        'restaurant.es',
      ]),
    ).toEqual(['base.apps.add', 'base.systemPlan.tabs.plan']);
  });
});

describe('loadCatalog', () => {
  it('reads the SPA catalogues and the Django ones under a checkout', () => {
    const root = mkdtempSync(join(tmpdir(), 'catalog-'));
    const write = (path: string, text: string) => {
      mkdirSync(join(root, path, '..'), { recursive: true });
      writeFileSync(join(root, path), text);
    };
    write('base/frontend/locale/en.json', JSON.stringify({ a: 'Home' }));
    write('base/frontend/locale/es.json', JSON.stringify({ a: 'Inicio' }));
    write('apps/sale/frontend/locale/en.json', JSON.stringify({ b: 'Sales' }));
    write('apps/sale/frontend/locale/es.json', JSON.stringify({ b: 'Ventas' }));
    write('packages/ui/src/shell/locales/en.json', JSON.stringify({ c: 'Open menu' }));
    write('packages/ui/src/shell/locales/es.json', JSON.stringify({ c: 'Abrir menú' }));
    write('apps/sale/locale/es/LC_MESSAGES/django.po', 'msgid "Sale"\nmsgstr "Venta"\n');
    write('node_modules/x/locale/es/LC_MESSAGES/django.po', 'msgid "Ignored"\nmsgstr "Ignorado"\n');
    const catalog = loadCatalog(root);
    expect([...catalog.en].sort()).toEqual(['Home', 'Open menu', 'Sale', 'Sales']);
    expect([...catalog.es].sort()).toEqual(['Abrir menú', 'Inicio', 'Venta', 'Ventas']);
  });
});
