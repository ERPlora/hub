import type { SettingsSchemaProperty } from '@erplora/module-types';

export type ModuleSettingControl = 'toggle' | 'select' | 'number' | 'text';

/**
 * Algunos módulos persisten flags en columnas INTEGER por paridad SQLite/PostgreSQL y publican
 * `enum: [0, 1]`. Para la persona usuaria siguen siendo booleanos: el detalle físico no debe
 * escapar al formulario.
 */
export function isStoredBoolean(prop: SettingsSchemaProperty): boolean {
  if (prop.type === 'boolean') return true;
  if (prop.type !== 'integer' || prop.enum?.length !== 2) return false;
  const values = new Set(prop.enum);
  return values.has(0) && values.has(1);
}

export function settingControl(prop: SettingsSchemaProperty): ModuleSettingControl {
  if (isStoredBoolean(prop)) return 'toggle';
  if (prop.enum?.length) return 'select';
  if (prop.type === 'integer' || prop.type === 'number') return 'number';
  return 'text';
}

/** Convierte la representación persistida a la representación del control. */
export function settingValueForControl(
  prop: SettingsSchemaProperty,
  value: unknown,
): unknown {
  if (!isStoredBoolean(prop)) return value;
  if (prop.type === 'boolean' && typeof value === 'boolean') return value;
  if (value === 0) return false;
  if (value === 1) return true;
  throw new TypeError('boolean setting must be boolean or 0/1');
}

/** Convierte el valor del control a la representación declarada por el schema. */
export function settingValueForStorage(
  prop: SettingsSchemaProperty,
  value: unknown,
): unknown {
  if (!isStoredBoolean(prop)) return value;
  if (typeof value !== 'boolean') throw new TypeError('boolean setting must be boolean');
  return prop.type === 'integer' ? (value ? 1 : 0) : value;
}

/**
 * Heading of the shell-owned tabs of a module (Plan, Settings) — hub#959.
 *
 * The nav entries carry `module_name` already localised by the runtime (ADR-0055); the manifest
 * carries the raw source-language `name`. Prefer the localised one; fall back to the manifest for
 * modules without nav entries; and to the id when even that is missing.
 */
export function shellTabHeading(
  tabs: ReadonlyArray<{ moduleName: string }>,
  manifest: { name?: string } | null | undefined,
  moduleId: string,
): string {
  return tabs[0]?.moduleName || manifest?.name || moduleId;
}
