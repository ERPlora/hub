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
  fields?: Record<
    string,
    {
      label?: string;
      description?: string;
      /**
       * The `enum` OPTIONS of this property, translated — keyed by the RAW value the schema
       * declares (hub#1427). `{ "dine_in": "En sala" }`.
       *
       * The other half of hub#1094: the label of the field was translatable, its options were not,
       * so a `select` painted `dine_in · takeaway · delivery` on a Spanish hub no matter what the
       * module shipped. Keyed by the stored value on purpose — the schema stays canonical English
       * (ADR-0055) and what gets saved never changes, only what is painted.
       */
      options?: Record<string, string | undefined>;
    } | undefined
  >;
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

/**
 * Label of ONE OPTION of an `enum` field — hub#1427.
 *
 * Order: **module locale → the raw value**. There is no schema fallback because JSON Schema has
 * nowhere to name an option: `enum` is a list of stored values, and those values are the contract
 * with the column. So the raw value is the last resort here for the same reason
 * [`humanizeSettingKey`] is for a label — a nameless option is worse than an English one.
 *
 * Looked up by the value's TEXT (`String(value)`), which is also how a JSON object can key it: a
 * numeric `enum` (`[1, 2]`) is written `{ "2": "Dos copias" }` in `locales/<lang>.json`.
 */
export function settingsOptionLabel(
  locale: ModuleSettingsLocale | undefined,
  key: string,
  value: string | number,
): string {
  const raw = String(value);
  return translated(locale?.fields?.[key]?.options?.[raw]) ?? raw;
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
 * The custom element that runs the TEST action of one setting, or `undefined` when the module
 * declares none for it — hub#1426.
 *
 * `x-erplora-preview` on the property names the module's Web Component. The shell paints the
 * button and calls `preview({ key, value, settings })` on that element with the value that is IN
 * THE FORM, unsaved; what "test" means is the module's business (playing a chime, flashing a
 * screen), and the shell deliberately knows nothing about it.
 *
 * It is an `x-` keyword of the module's OWN settings JSON Schema and not a `module.json` field, so
 * it needs no manifest surface at all: the annotation sits on the very property it describes, and
 * a JSON Schema validator ignores keywords it does not know.
 *
 * A blank or non-dashed tag is treated as "not declared": `document.createElement` of a name that
 * is not a valid custom element would silently give back an `HTMLUnknownElement` with no `preview`
 * on it, and the button would then be a button that does nothing.
 */
export function settingsPreviewTag(prop: SettingsSchemaProperty): string | undefined {
  const tag = prop['x-erplora-preview']?.trim();
  return tag && /^[a-z][a-z0-9]*-[a-z0-9-]+$/.test(tag) ? tag : undefined;
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
