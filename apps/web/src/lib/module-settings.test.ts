import { describe, expect, it } from 'vitest';
import type { SettingsSchemaProperty } from '@erplora/module-types';

import {
  isStoredBoolean,
  settingControl,
  settingValueForControl,
  settingValueForStorage,
  settingsFieldDescription,
  settingsFieldLabel,
  settingsHeading,
  shellTabHeading,
  type ModuleSettingsLocale,
} from './module-settings';

describe('formulario genérico de ajustes', () => {
  const inventoryFlag: SettingsSchemaProperty = {
    type: 'integer',
    enum: [0, 1],
    default: 1,
    title: 'Controlar stock',
  };
  const nativeFlag: SettingsSchemaProperty = {
    type: 'boolean',
    default: false,
    title: 'Enviar avisos',
  };

  it('trata un flag INTEGER 0/1 de Inventory como toggle y conserva su frontera', () => {
    expect(isStoredBoolean(inventoryFlag)).toBe(true);
    expect(settingControl(inventoryFlag)).toBe('toggle');
    expect(settingValueForControl(inventoryFlag, 0)).toBe(false);
    expect(settingValueForControl(inventoryFlag, 1)).toBe(true);
    expect(settingValueForStorage(inventoryFlag, false)).toBe(0);
    expect(settingValueForStorage(inventoryFlag, true)).toBe(1);
  });

  it('mantiene como booleano un flag nativo de cualquier otro módulo', () => {
    expect(isStoredBoolean(nativeFlag)).toBe(true);
    expect(settingControl(nativeFlag)).toBe('toggle');
    expect(settingValueForControl(nativeFlag, true)).toBe(true);
    expect(settingValueForStorage(nativeFlag, false)).toBe(false);
  });

  it('rechaza representaciones ambiguas en vez de mostrar o guardar números libres', () => {
    expect(() => settingValueForControl(inventoryFlag, 10)).toThrow(TypeError);
    expect(() => settingValueForStorage(inventoryFlag, 1)).toThrow(TypeError);
  });

  it('no confunde otros enums numéricos con flags', () => {
    const quantity: SettingsSchemaProperty = { type: 'integer', enum: [1, 10] };
    expect(isStoredBoolean(quantity)).toBe(false);
    expect(settingControl(quantity)).toBe('select');
  });
});

describe('heading of the shell-owned tabs (Plan, Settings) — hub#959', () => {
  // The nav entries carry `module_name` already localised by the runtime (ADR-0055); the manifest
  // carries the raw source-language `name`. The Settings tab of Sales read "Sales & POS" in a
  // Spanish hub because it took the manifest first.
  it('prefers the localised name from the nav entries over the raw manifest name', () => {
    expect(
      shellTabHeading([{ moduleName: 'Ventas / TPV' }], { name: 'Sales & POS' }, 'sales'),
    ).toBe('Ventas / TPV');
  });

  it('falls back to the manifest name when the module has no nav entry, and to the id last', () => {
    expect(shellTabHeading([], { name: 'Sales & POS' }, 'sales')).toBe('Sales & POS');
    expect(shellTabHeading([], null, 'sales')).toBe('sales');
  });
});

// ── hub#1094: the generic Settings screen reads the module's LOCALE, not only its JSON Schema ──
//
// The screen the shell generates for ANY module came out entirely in English on a Spanish hub:
// `prop.title || humanize(key)` reads the JSON Schema, which is a canonical-English artefact
// (ADR-0055), and when the module ships no `title` it falls back to the COLUMN NAME
// (`warning_time_minutes` → `Warning Time Minutes`). No lookup in `locales/` existed at all, so the
// screen could not be in Spanish whatever the module did.
//
// The order pinned here is the one `kitchen` already ships (ERPlora/kitchen#41, v2.3.19):
// locale → schema `title` → `humanize(key)`, with `humanize` as the last, noisy resort.
describe('hub#1094 · the labels of the generic settings form come from the module locale', () => {
  const warningTime: SettingsSchemaProperty = { type: 'integer', title: 'Amber warning (minutes)' };
  const untitled: SettingsSchemaProperty = { type: 'integer' };

  const locale: ModuleSettingsLocale = {
    title: 'Cocina',
    fields: {
      warning_time_minutes: { label: 'Aviso ámbar (minutos)', description: 'Cuándo se pone ámbar' },
    },
  };

  it('prefers the locale label over the schema title', () => {
    expect(settingsFieldLabel(locale, 'warning_time_minutes', warningTime)).toBe(
      'Aviso ámbar (minutos)',
    );
  });

  it('falls back to the schema title when the locale does not translate that field', () => {
    expect(settingsFieldLabel(locale, 'critical_time_minutes', warningTime)).toBe(
      'Amber warning (minutes)',
    );
  });

  it('falls back to the humanized key only when neither locale nor schema names the field', () => {
    expect(settingsFieldLabel(undefined, 'warning_time_minutes', untitled)).toBe(
      'Warning Time Minutes',
    );
  });

  it('ignores an empty locale string instead of painting a blank label', () => {
    const blank: ModuleSettingsLocale = { fields: { warning_time_minutes: { label: '   ' } } };
    expect(settingsFieldLabel(blank, 'warning_time_minutes', warningTime)).toBe(
      'Amber warning (minutes)',
    );
  });

  it('translates the help text with the same order, and stays undefined when nobody writes one', () => {
    expect(settingsFieldDescription(locale, 'warning_time_minutes', warningTime)).toBe(
      'Cuándo se pone ámbar',
    );
    expect(
      settingsFieldDescription(locale, 'items_per_page', { type: 'integer', description: 'How many' }),
    ).toBe('How many');
    expect(settingsFieldDescription(locale, 'items_per_page', untitled)).toBeUndefined();
  });

  it('translates the heading of the screen: `settings.title` of the locale wins over the manifest', () => {
    expect(settingsHeading(locale, { schema: 's', get: 'g', set: 's', title: 'Kitchen' })).toBe(
      'Cocina',
    );
    expect(settingsHeading(undefined, { schema: 's', get: 'g', set: 's', title: 'Kitchen' })).toBe(
      'Kitchen',
    );
    expect(settingsHeading(undefined, { schema: 's', get: 'g', set: 's' })).toBeUndefined();
  });

  it('drops the heading when it only repeats what the bar of the screen already says', () => {
    // Most modules name their settings block after the module, so this is the COMMON case, not
    // the edge one: «Cocina» over «Cocina» is noise, and the shell already paints the top one.
    expect(
      settingsHeading(locale, { schema: 's', get: 'g', set: 's', title: 'Kitchen' }, 'Cocina'),
    ).toBeUndefined();
    expect(
      settingsHeading(locale, { schema: 's', get: 'g', set: 's', title: 'Kitchen' }, 'Comandas'),
    ).toBe('Cocina');
  });
});
