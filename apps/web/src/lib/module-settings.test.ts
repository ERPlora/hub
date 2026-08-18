import { describe, expect, it } from 'vitest';
import type { SettingsSchemaProperty } from '@erplora/module-types';

import {
  isStoredBoolean,
  settingControl,
  settingValueForControl,
  settingValueForStorage,
  shellTabHeading,
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
