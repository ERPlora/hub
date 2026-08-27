import type { ModuleSettingsDef, SettingsSchemaProperty } from '@erplora/module-types';

export type ModuleSettingControl = 'toggle' | 'select' | 'number' | 'text';

/**
 * The `settings` block of a module's `locales/<lang>.json` (ADR-0055) — hub#1094.
 *
 * The generic Settings screen used to read ONLY the JSON Schema, which is a canonical-English
 * artefact: on a Spanish hub the whole screen came out in English, and for a property with no
 * `title` it painted the COLUMN NAME (`warning_time_minutes` → `Warning Time Minutes`). The module
 * had nowhere to be read from — `kitchen` and `tables` had shipped these very keys for weeks and
 * the shell ignored them.
 *
 * Shape is the one the modules already publish (`ERPlora/kitchen#41`, v2.3.19):
 * `settings.title` and `settings.fields.<key>.{label,description}`.
 */
export interface ModuleSettingsLocale {
  /** Heading of the settings screen, translated. Mirrors `settings.title` of the manifest. */
  title?: string;
  /** Per-property strings, keyed by the JSON Schema property name. */
  fields?: Record<string, { label?: string; description?: string } | undefined>;
}

/**
 * A translated string, or `undefined` when nobody wrote one.
 *
 * Blank-but-present is treated as absent on purpose: a module that ships `"label": "  "` would
 * otherwise paint an empty label, which is strictly worse than the English it replaced.
 */
function translated(value: string | undefined): string | undefined {
  const text = value?.trim();
  return text ? text : undefined;
}

/** "humanizes" a snake_case key → "Title Case", the last resort when nobody names the field. */
export function humanizeSettingKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Label of one field of the generic settings form — hub#1094.
 *
 * Order: **module locale → schema `title` → humanized key**. The schema is canonical English
 * (ADR-0055), so it can only ever be the fallback; `humanize` is the noisy last resort that leaks
 * the column name and exists only so a field is never nameless.
 */
export function settingsFieldLabel(
  locale: ModuleSettingsLocale | undefined,
  key: string,
  prop: SettingsSchemaProperty,
): string {
  return (
    translated(locale?.fields?.[key]?.label) ??
    translated(prop.title) ??
    humanizeSettingKey(key)
  );
}

/** Help text of one field, same order as [`settingsFieldLabel`]. `undefined` when nobody wrote one. */
export function settingsFieldDescription(
  locale: ModuleSettingsLocale | undefined,
  key: string,
  prop: SettingsSchemaProperty,
): string | undefined {
  return translated(locale?.fields?.[key]?.description) ?? translated(prop.description);
}

/**
 * Heading painted INSIDE the settings form (module-system.md §3quater says `settings.title` is the
 * heading of the form — it just was never rendered, and never translated). Locale wins over the
 * manifest; `undefined` when the module declares no title, and then the form paints no heading.
 *
 * `pageTitle` is what the shell ALREADY shows in the topbar (the module's localised name), and a
 * heading equal to it is repeated, not informative: with `kitchen` translated, both would read
 * «Cocina», one under the other. Most modules name their settings block after the module, so
 * without this the common case would be the ugly one. Pass nothing to always paint it.
 */
export function settingsHeading(
  locale: ModuleSettingsLocale | undefined,
  def: ModuleSettingsDef,
  pageTitle?: string,
): string | undefined {
  const title = translated(locale?.title) ?? translated(def.title);
  if (!title) return undefined;
  return title === translated(pageTitle) ? undefined : title;
}

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
