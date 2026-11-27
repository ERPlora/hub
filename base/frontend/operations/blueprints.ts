// Types of base/schemas/blueprints.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

export type BlueprintPurpose = 'backup' | 'template';
/** How a dataset of a load went (`base.DatasetStatus`). */
export type DatasetStatus = 'applied' | 'partial' | 'already' | 'failed' | 'empty' | 'discarded';
/** How an app of a load went (`base.AppLoadStatus`). */
export type AppLoadStatus = DatasetStatus | 'inactive' | 'unknown' | 'not_selected' | 'waiting' | 'setup_failed';
export type ImportStatus = 'complete' | 'partial' | 'failed';

export interface BlueprintApp {
  id: string;
  label: string;
}

/** «<app>.<what>»: a dataset, e.g. «inventory.product». */
export interface BlueprintPart {
  key: string;
  label: string;
  rows: number;
}

/** `base.TemplateOut`: a seed of the catalogue. */
export interface Template {
  /** «<vertical>.<language>». */
  key: string;
  name: string;
  description: string;
  language: string;
  /** ISO 3166. */
  country: string;
  vertical: string;
  version: string;
  apps: BlueprintApp[];
  contents: BlueprintPart[];
}

export interface BlueprintDataset extends BlueprintPart {
  personal: boolean;
  /** False: left out of this load (personal data in a template). */
  travels: boolean;
}

export interface BlueprintAppSummary extends BlueprintApp {
  /** «turns_on»: off here, the load turns it on first and then loads it; «inactive»: left off. */
  status: 'on' | 'turns_on' | 'inactive' | 'unknown';
  datasets: BlueprintDataset[];
}

/** `base.BlueprintSummaryOut`: what a template or a file brings, before loading it. */
export interface BlueprintSummary {
  name: string;
  language: string;
  country: string;
  purpose: BlueprintPurpose;
  /** Empty for a template of the catalogue. */
  created_at: string;
  /** Empty for a file. */
  version: string;
  source: 'catalog' | 'file';
  apps: BlueprintAppSummary[];
  /** Parts of the file this hub never loads (people, fiscal data…), already in words. */
  dropped: string[];
}

export interface DatasetLoad extends BlueprintPart {
  status: DatasetStatus;
  created: number;
  already: number;
  failed: number;
  problems: string[];
}

export interface AppLoad extends BlueprintApp {
  status: AppLoadStatus;
  /** Why an app of the blueprint that was off could not be turned on («inactive»), in words; empty otherwise. */
  reason?: string;
  datasets: DatasetLoad[];
}

export interface LoadReport {
  status: ImportStatus;
  apps: AppLoad[];
  dropped: string[];
}

export type RetryBlocked = '' | 'file' | 'version_gone' | 'complete' | 'undone' | 'waiting';

/** `base.ImportOut`: one load and its report. */
export interface ImportRow {
  id: string;
  name: string;
  source: 'catalog' | 'file';
  template_key: string;
  status: ImportStatus;
  created_at: string;
  created_by: string;
  /** Rows it created. */
  rows: number;
  undone: boolean;
  undoable: boolean;
  retry: boolean;
  retry_blocked: RetryBlocked;
  report: LoadReport;
}

export interface BlueprintSource {
  template?: string;
  file_base64?: string;
}

export interface BlueprintImportInput extends BlueprintSource {
  /** The apps to load; none = every app of the blueprint. */
  apps?: string[] | null;
  /** A load that did not go in whole: load again what did not. */
  retry_of?: string | null;
}

export interface BlueprintExportInput {
  name: string;
  language: string;
  purpose: BlueprintPurpose;
  apps: string[];
  data: string[];
  /** Of the apps whose data travels, the datasets chosen; an app none of whose datasets is named takes all. */
  datasets: string[];
}

export interface DatasetCount extends BlueprintPart {
  personal: boolean;
}

export interface AppDatasets extends BlueprintApp {
  icon: string;
  /** Empty: the app travels without data of its own. */
  datasets: DatasetCount[];
  /** It has data of its own that does not travel in the file (its history, its people, its settings…). */
  keeps_data: boolean;
}

export interface Removal extends BlueprintApp {
  removed: number;
  failed: number;
  problems: string[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.blueprint.list': { input: NoInput; output: { templates: Template[]; empty: boolean } };
    'base.blueprint.inspect': { input: BlueprintSource; output: BlueprintSummary };
    'base.blueprint.import': { input: BlueprintImportInput; output: ImportRow };
    'base.blueprint.export': {
      input: BlueprintExportInput;
      output: { filename: string; content_type: string; content_base64: string };
    };
    'base.import.list': { input: NoInput; output: { imports: ImportRow[]; unfinished: ImportRow | null } };
    'base.import.undo': { input: { id: string }; output: { id: string; apps: Removal[] } };
    'base.dataset.list': { input: NoInput; output: { apps: AppDatasets[] } };
  }
}
