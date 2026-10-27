// The rules of Settings › Data that are not the server's (BASE-G101–G109, BASE-G131; the old hub's `ExportPanel.vue`,
// `import-retry.ts`, `data-table-labels.ts` and `blueprint-hero.ts`): the address of the page, what an export takes,
// how a report reads and what the Home's templates card offers. Pure: the components only paint them.
import type { StatusPillTone } from '@erplora/ui/components';

import type {
  AppDatasets,
  AppLoadStatus,
  BlueprintExportInput,
  BlueprintPurpose,
  ImportRow,
  LoadReport,
  RetryBlocked,
  Template,
} from '../operations';

// ── The address ──────────────────────────────────────────────────────────────────────────────────────────────────

// The old hub's tabs, in its order and with its addresses: «General» first (APP-BASE-3), Business and Printing
// (APP-BASE-6), then «Data and backups» (APP-BASE-2).
export type SettingsTab = 'general' | 'business' | 'tickets' | 'data';
export const SETTINGS_TABS: readonly SettingsTab[] = ['general', 'business', 'tickets', 'data'];
/** Old addresses still linked: `#hub` was General; published versions of VeriFactu open `#tax`, the business's tab. */
const SETTINGS_TAB_ALIASES: Readonly<Record<string, SettingsTab>> = { hub: 'general', tax: 'business' };

/** The tab a hash opens (`#data`); one it does not have — the old `#store`, `#permissions`… — opens the first, as the old hub. */
export function settingsTab(hash: string): SettingsTab {
  const wanted = hash.replace(/^#/, '');
  return SETTINGS_TABS.find((tab) => tab === wanted) ?? SETTINGS_TAB_ALIASES[wanted] ?? SETTINGS_TABS[0];
}

export type DataSection = 'import' | 'export' | 'reset';
export const DATA_SECTIONS: readonly DataSection[] = ['import', 'export', 'reset'];

/** The section `?data=` names; Import otherwise (the old hub's `?data=export`). */
export function dataSection(query: unknown): DataSection {
  const value = Array.isArray(query) ? query[0] : query;
  return DATA_SECTIONS.find((section) => section === value) ?? 'import';
}

// ── The export (BASE-G101, BASE-G102) ────────────────────────────────────────────────────────────────────────────

/** Django's `slugify`, the one the server names the file with. */
function slugify(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[^\x00-\x7F]/g, '')
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/[-\s]+/g, '-')
    .replace(/^[-_]+|[-_]+$/g, '');
}

/** «{name}_{language}.blueprint.zip», as `base.blueprint.file_name` writes it. */
export function exportFileName(name: string, language: string): string {
  return `${slugify(name) || 'blueprint'}_${slugify(language) || 'xx'}.blueprint.zip`;
}

/** The file's name to start with: the business's, or its address while it has none (as the server's `confirm_with`). */
export function defaultExportName(business: string | undefined, hostname: string): string {
  return business?.trim() || hostname.split('.')[0] || '';
}

/** What the person ticked: the apps registered, the ones whose data travels and the tables unmarked. */
export interface ExportChoice {
  apps: ReadonlySet<string>;
  data: ReadonlySet<string>;
  /** Tables left out: none = all of them, so a new table of an app never stays out unseen. */
  excluded: ReadonlySet<string>;
}

/** Every app registered and no data, as the old hub opens it. */
export function freshExportChoice(apps: readonly AppDatasets[]): ExportChoice {
  return { apps: new Set(apps.map((app) => app.id)), data: new Set(), excluded: new Set() };
}

function toggled(set: ReadonlySet<string>, id: string, on: boolean): Set<string> {
  const next = new Set(set);
  if (on) next.add(id);
  else next.delete(id);
  return next;
}

/** Unmarking an app unmarks its data too: its data travels only with it. */
export function toggleApp(choice: ExportChoice, app: string, on: boolean): ExportChoice {
  return { ...choice, apps: toggled(choice.apps, app, on), data: on ? choice.data : toggled(choice.data, app, false) };
}

export function toggleData(choice: ExportChoice, app: string, on: boolean): ExportChoice {
  return { ...choice, data: toggled(choice.data, app, on && choice.apps.has(app)) };
}

export function toggleDataset(choice: ExportChoice, key: string, on: boolean): ExportChoice {
  return { ...choice, excluded: toggled(choice.excluded, key, !on) };
}

/** «Select all» marks every app and its data; «Deselect all» leaves the file without any app. */
export function selectAll(apps: readonly AppDatasets[], on: boolean): ExportChoice {
  const ids = on ? apps.map((app) => app.id) : [];
  return { apps: new Set(ids), data: new Set(ids), excluded: new Set() };
}

/** A table of `app` that can travel for `purpose`: personal data only in a backup. */
export function travels(dataset: { personal: boolean }, purpose: BlueprintPurpose): boolean {
  return purpose === 'backup' || !dataset.personal;
}

/** The input of `base.blueprint.export`: an app's data travels only with tables of its own left to take. */
export function exportInput(
  choice: ExportChoice,
  apps: readonly AppDatasets[],
  file: { name: string; language: string; purpose: BlueprintPurpose },
): BlueprintExportInput {
  const registered = apps.filter((app) => choice.apps.has(app.id));
  const data: string[] = [];
  const datasets: string[] = [];
  for (const app of registered) {
    if (!choice.data.has(app.id)) continue;
    const offered = app.datasets.filter((dataset) => travels(dataset, file.purpose));
    const kept = offered.filter((dataset) => !choice.excluded.has(dataset.key));
    if (!kept.length) continue;
    data.push(app.id);
    if (kept.length < offered.length) datasets.push(...kept.map((dataset) => dataset.key));
  }
  return { ...file, apps: registered.map((app) => app.id), data, datasets };
}

/** The bytes of a file in base64, in chunks: a spread of 5 MB would blow the call stack. */
export function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const CHUNK = 0x8000;
  for (let start = 0; start < bytes.length; start += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(start, start + CHUNK));
  }
  return btoa(binary);
}

export function base64ToBlob(content: string, type: string): Blob {
  const binary = atob(content);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type });
}

/** Hands the browser a file: a Blob saved through a temporary link, never added to the page. */
export function saveFile(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

// ── The import (BASE-G103–G108) ──────────────────────────────────────────────────────────────────────────────────

/** The server takes 5 MB of zip at most (`base.blueprint`). */
export const MAX_FILE_BYTES = 5 * 1024 * 1024;

function folded(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
}

/** «Search templates»: by name, description or the name of an app it brings. */
export function templateMatches(template: Template, search: string): boolean {
  const wanted = folded(search.trim());
  if (!wanted) return true;
  return [template.name, template.description, ...template.apps.map((app) => app.label)].some((text) =>
    folded(text).includes(wanted),
  );
}

type KnownStatus = AppLoadStatus;

/** The words of each status of a report (the old hub's «Applied», «Skipped»… with the new ones). */
export const STATUS_KEY: Record<KnownStatus, string> = {
  applied: 'base.data.status.applied',
  partial: 'base.data.status.partial',
  already: 'base.data.status.already',
  failed: 'base.data.status.failed',
  empty: 'base.data.status.empty',
  discarded: 'base.data.status.discarded',
  inactive: 'base.data.status.inactive',
  unknown: 'base.data.status.unknown',
  not_selected: 'base.data.status.notSelected',
};

const STATUS_TONE: Record<KnownStatus, StatusPillTone> = {
  applied: 'success',
  partial: 'warning',
  already: 'neutral',
  failed: 'danger',
  empty: 'neutral',
  discarded: 'neutral',
  inactive: 'warning',
  unknown: 'warning',
  not_selected: 'neutral',
};

/** A status in words and tone; one this screen does not know is a failure with its own text, never a success. */
export function statusPill(status: string): { tone: StatusPillTone; key: string; raw?: string } {
  if (status in STATUS_KEY) return { tone: STATUS_TONE[status as KnownStatus], key: STATUS_KEY[status as KnownStatus] };
  return { tone: 'danger', key: STATUS_KEY.failed, raw: status };
}

/** Why a load cannot be retried, in words (the server's `retry_blocked`). */
export const RETRY_BLOCKED_KEY: Record<Exclude<RetryBlocked, ''>, string> = {
  file: 'base.data.retry.blocked.file',
  version_gone: 'base.data.retry.blocked.versionGone',
  complete: 'base.data.retry.blocked.complete',
  undone: 'base.data.retry.blocked.undone',
};

/** The apps of a report that did not go in (failed, in part, or off because the load could not turn them on and
 * says why), by name. */
export function unloaded(report: LoadReport): string[] {
  return report.apps
    .filter((app) => app.status === 'failed' || app.status === 'partial' || (app.status === 'inactive' && !!app.reason))
    .map((app) => app.label);
}

// ── The Home's templates card (BASE-G131, BASE-F02) ──────────────────────────────────────────────────────────────

/** The card offers at most four, one per kind of business, in the catalogue's order (the hub's country, then the
 * person's language): of a vertical in two languages, the first the catalogue gives, theirs when it has it. */
export const CARD_TEMPLATES = 4;

export function cardTemplates(templates: readonly Template[]): Template[] {
  const firstOfEachVertical = new Map<string, Template>();
  for (const item of templates) {
    if (!firstOfEachVertical.has(item.vertical)) firstOfEachVertical.set(item.vertical, item);
  }
  return [...firstOfEachVertical.values()].slice(0, CARD_TEMPLATES);
}

/** How a load from the card went: all in, in part (what did not), or nothing. */
export function cardOutcome(load: ImportRow): { kind: 'ready' | 'partial' | 'failed'; missing: string[] } {
  if (load.status === 'complete') return { kind: 'ready', missing: [] };
  return { kind: load.status === 'failed' ? 'failed' : 'partial', missing: unloaded(load.report) };
}
