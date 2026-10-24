// Files (APP-BASE-8; the old hub's `lib/media.ts` and `file-preview.ts`): what the screen works out by itself. The
// server (`base.file.*`, `base/files.py`) decides and refuses; here, sizes as people read them, the tree flattened for
// the narrow selector and «Move to…», where the screen goes after a rename, a move or a delete of the folder it shows,
// the search of the open folder, a CSV for the preview, and the sentence of each refusal the server gives (hub#1776).

/** The heaviest file the server takes (`base.files.MAX_FILE_BYTES`): refused here before sending 33 MB of base64. */
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
/** The pages of a PDF the preview draws (the old hub's); a longer one says so and offers the download. */
export const PDF_PAGES = 30;
/** The characters of a text the preview shows; a longer one says so. */
export const TEXT_PREVIEW_CHARS = 1_000_000;
/** The rows of a CSV the preview shows. */
export const TABLE_PREVIEW_ROWS = 500;
/** The longest name of a new folder (`base.files.MAX_FOLDER_NAME`) and of a name (255 bytes on the server). */
export const MAX_FOLDER_NAME = 100;
export const MAX_NAME = 255;

export type FilePreview = 'image' | 'pdf' | 'text' | 'table' | 'json' | 'audio' | 'video' | '';

export interface FolderNode {
  path: string;
  name: string;
  children: FolderNode[];
}

export interface FlatFolder {
  path: string;
  name: string;
  depth: number;
}

const KB = 1024;
const MB = KB * 1024;
const GB = MB * 1024;

/** «512 B», «2 KB», «1,5 MB», «5 GB» (the old hub's `human_bytes`, in the person's language). */
export function formatSize(bytes: number, locale: string): string {
  const number = (value: number, decimals: number) =>
    new Intl.NumberFormat(locale, { maximumFractionDigits: decimals }).format(value);
  if (bytes >= GB) return `${number(bytes / GB, 1)} GB`;
  if (bytes >= MB) return `${number(bytes / MB, bytes / MB >= 100 ? 0 : 1)} MB`;
  if (bytes >= KB) return `${number(bytes / KB, 0)} KB`;
  return `${bytes} B`;
}

export function tooLarge(bytes: number): boolean {
  return bytes > MAX_UPLOAD_BYTES;
}

/** Every folder of the tree, in order, with how deep it is. */
export function flatFolders(tree: readonly FolderNode[], depth = 0): FlatFolder[] {
  return tree.flatMap((node) => [
    { path: node.path, name: node.name, depth },
    ...flatFolders(node.children, depth + 1),
  ]);
}

/** The folders inside `folder` (`''`: the top ones); none for a folder the tree does not have. */
export function childrenOf(tree: readonly FolderNode[], folder: string): FolderNode[] {
  if (!folder) return [...tree];
  for (const node of tree) {
    if (node.path === folder) return [...node.children];
    if (folder.startsWith(`${node.path}/`)) return childrenOf(node.children, folder);
  }
  return [];
}

export function parentOf(path: string): string {
  const slash = path.lastIndexOf('/');
  return slash < 0 ? '' : path.slice(0, slash);
}

export function nameOf(path: string): string {
  return path.slice(path.lastIndexOf('/') + 1);
}

/** A name as the list cuts it: what it says (`stem`, cut with an ellipsis when it does not fit) and its extension
 *  (`.pdf`, always whole), as the server reads one: after the last dot, with something before it, a short word.
 *  A folder (`folder`) is all stem. */
export function splitName(name: string, folder = false): { stem: string; extension: string } {
  const dot = name.lastIndexOf('.');
  const extension = name.slice(dot + 1);
  return folder || dot <= 0 || !/^[^\s.]{1,10}$/.test(extension)
    ? { stem: name, extension: '' }
    : { stem: name.slice(0, dot), extension: name.slice(dot) };
}

const inside = (path: string, folder: string) => path === folder || path.startsWith(`${folder}/`);

/** The open folder once `from` became `to` (a rename or a move): it follows when it is `from` or inside it. */
export function afterMove(open: string, from: string, to: string): string {
  return inside(open, from) ? to + open.slice(from.length) : open;
}

/** The open folder once `deleted` is gone: the folder above it when the open one was it or inside it. */
export function afterDelete(open: string, deleted: string): string {
  return inside(open, deleted) ? parentOf(deleted) : open;
}

function folded(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
}

/** «Search files…», in the open folder: any part of the name, whatever the capitals or the accents. */
export function matches(name: string, search: string): boolean {
  const wanted = folded(search.trim());
  return !wanted || folded(name).includes(wanted);
}

/** Where the hub serves a file to the person who may see it (`base.file.read`); never the bucket's. */
export function rawUrl(path: string, inline = false): string {
  const query = new URLSearchParams({ path });
  if (inline) query.set('inline', 'true');
  return `/api/files/raw?${query.toString()}`;
}

/** A CSV (`,`) or TSV (`\t`) as rows: quoted fields with their separators, line breaks and doubled quotes. */
export function parseTable(text: string, separator: string, limit = TABLE_PREVIEW_ROWS): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length && rows.length < limit; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"' && field === '') {
      quoted = true;
    } else if (char === separator) {
      row.push(field);
      field = '';
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else {
      field += char;
    }
  }
  if ((field !== '' || row.length) && rows.length < limit) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

const ICONS: Record<FilePreview, string> = {
  image: 'ion:image-outline',
  pdf: 'ion:receipt-outline',
  text: 'ion:code-slash-outline',
  table: 'ion:grid-outline',
  json: 'ion:code-slash-outline',
  audio: 'ion:play-circle-outline',
  video: 'ion:play-circle-outline',
  '': 'ion:file-tray-outline',
};

export function iconFor(preview: FilePreview): string {
  return ICONS[preview];
}

/** The sentence of each refusal, by the code the server (or the SDK) gives it. */
export const REFUSAL_KEYS: Readonly<Record<string, string>> = {
  'base.file_invalid_name': 'base.files.refusal.invalidName',
  'base.file_invalid_path': 'base.files.refusal.missing',
  'base.file_folder_missing': 'base.files.refusal.folderMissing',
  'base.file_missing': 'base.files.refusal.missing',
  'base.file_exists': 'base.files.refusal.exists',
  'base.file_already_there': 'base.files.refusal.alreadyThere',
  'base.file_move_into_itself': 'base.files.refusal.intoItself',
  'base.file_type_refused': 'base.files.refusal.typeRefused',
  'base.file_too_large': 'base.files.refusal.tooLarge',
  payload_too_large: 'base.files.refusal.tooLarge',
  'base.file_no_space': 'base.files.refusal.noSpace',
  'base.file_not_base64': 'base.files.refusal.notWhole',
  'base.file_store_unavailable': 'base.files.refusal.storeUnavailable',
  permission_denied: 'base.files.refusal.onlyAdmin',
  unauthorized: 'base.files.refusal.sessionExpired',
  network_error: 'base.files.refusal.connection',
};

export function refusalKey(code: string | undefined): string {
  return (code && REFUSAL_KEYS[code]) || 'base.files.refusal.generic';
}

/** The extension of a name, for «Programs (.exe) can't be kept…»; `''` without one. */
export function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
}
