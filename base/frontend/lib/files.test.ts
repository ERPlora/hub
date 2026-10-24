// Files (APP-BASE-8, BASE-G82…G86): what the screen works out by itself — sizes as people read them, the folders of
// the tree flattened for the narrow selector and «Move to…», where the screen goes after a rename, a move or a delete
// of the folder it shows, the search of the open folder, a CSV for the preview, and the sentence of every refusal
// the server can give (each code of `base/files.py`, never «check the connection» for all, hub#1776).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import {
  afterDelete,
  afterMove,
  childrenOf,
  type FolderNode,
  flatFolders,
  formatSize,
  iconFor,
  joinSentences,
  matches,
  MAX_UPLOAD_BYTES,
  nameOf,
  parentOf,
  parseTable,
  rawUrl,
  REFUSAL_KEYS,
  refusalKey,
  splitName,
  tooLarge,
} from './files';

const TREE: FolderNode[] = [
  { path: 'Contratos', name: 'Contratos', children: [] },
  {
    path: 'Facturas',
    name: 'Facturas',
    children: [
      { path: 'Facturas/2025', name: '2025', children: [] },
      { path: 'Facturas/2026', name: '2026', children: [{ path: 'Facturas/2026/marzo', name: 'marzo', children: [] }] },
    ],
  },
];

describe('sizes', () => {
  it('reads bytes as people do, in their language', () => {
    expect(formatSize(0, 'en')).toBe('0 B');
    expect(formatSize(512, 'en')).toBe('512 B');
    expect(formatSize(1536, 'en')).toBe('2 KB');
    expect(formatSize(1.5 * 1024 * 1024, 'en')).toBe('1.5 MB');
    expect(formatSize(1.5 * 1024 * 1024, 'es')).toBe('1,5 MB');
    expect(formatSize(250 * 1024 * 1024, 'en')).toBe('250 MB');
    expect(formatSize(5 * 1024 ** 3, 'es')).toBe('5 GB');
  });

  it('the screen refuses what the server would, before sending it: 25 MB', () => {
    expect(MAX_UPLOAD_BYTES).toBe(25 * 1024 * 1024);
    expect(tooLarge(MAX_UPLOAD_BYTES)).toBe(false);
    expect(tooLarge(MAX_UPLOAD_BYTES + 1)).toBe(true);
  });
});

describe('folders', () => {
  it('flattens the tree in order, with its depth, for the selector and «Move to…»', () => {
    expect(flatFolders(TREE)).toEqual([
      { path: 'Contratos', name: 'Contratos', depth: 0 },
      { path: 'Facturas', name: 'Facturas', depth: 0 },
      { path: 'Facturas/2025', name: '2025', depth: 1 },
      { path: 'Facturas/2026', name: '2026', depth: 1 },
      { path: 'Facturas/2026/marzo', name: 'marzo', depth: 2 },
    ]);
  });

  it('gives the folders inside the open one (the root: the top ones)', () => {
    expect(childrenOf(TREE, '').map((node) => node.name)).toEqual(['Contratos', 'Facturas']);
    expect(childrenOf(TREE, 'Facturas').map((node) => node.name)).toEqual(['2025', '2026']);
    expect(childrenOf(TREE, 'Facturas/2026/marzo')).toEqual([]);
    expect(childrenOf(TREE, 'Nadie')).toEqual([]);
  });

  it('knows a path’s folder and its name', () => {
    expect(parentOf('Facturas/2026/marzo.pdf')).toBe('Facturas/2026');
    expect(parentOf('marzo.pdf')).toBe('');
    expect(nameOf('Facturas/2026/marzo.pdf')).toBe('marzo.pdf');
  });
});

describe('where the screen goes', () => {
  it('follows the open folder when it, or one above it, is renamed or moved', () => {
    expect(afterMove('Facturas/2026', 'Facturas', 'Facturación')).toBe('Facturación/2026');
    expect(afterMove('Facturas', 'Facturas', 'Archivo/Facturas')).toBe('Archivo/Facturas');
    // A sibling whose name starts the same is not inside it.
    expect(afterMove('Facturas2026', 'Facturas', 'X')).toBe('Facturas2026');
    expect(afterMove('Contratos', 'Facturas', 'X')).toBe('Contratos');
  });

  it('goes up when the open folder, or one above it, is deleted', () => {
    expect(afterDelete('Facturas/2026', 'Facturas/2026')).toBe('Facturas');
    expect(afterDelete('Facturas/2026/marzo', 'Facturas')).toBe('');
    expect(afterDelete('Facturas2026', 'Facturas')).toBe('Facturas2026');
    expect(afterDelete('Contratos', 'Facturas/a.pdf')).toBe('Contratos');
  });
});

describe('search in the open folder', () => {
  it('finds by any part of the name, without caring for capitals or accents', () => {
    expect(matches('Facturación Marzo.pdf', 'facturacion')).toBe(true);
    expect(matches('Facturación Marzo.pdf', 'MARZO')).toBe(true);
    expect(matches('Facturación Marzo.pdf', '  ')).toBe(true);
    expect(matches('Facturación Marzo.pdf', 'abril')).toBe(false);
  });
});

describe('reading a file', () => {
  it('asks the hub for it, never the store: inline only when the page shows it', () => {
    expect(rawUrl('Facturas/marzo 2026.pdf')).toBe('/api/files/raw?path=Facturas%2Fmarzo+2026.pdf');
    expect(rawUrl('a&b.png', true)).toBe('/api/files/raw?path=a%26b.png&inline=true');
  });

  it('reads a CSV with its quotes, a TSV by tabs', () => {
    expect(parseTable('a,b\n"1,5","dijo ""hola"""\r\n3,4\n', ',')).toEqual([
      ['a', 'b'],
      ['1,5', 'dijo "hola"'],
      ['3', '4'],
    ]);
    expect(parseTable('a\tb\n1\t2', '\t')).toEqual([
      ['a', 'b'],
      ['1', '2'],
    ]);
  });

  it('paints each kind with an icon the shell has', () => {
    expect(iconFor('image')).toBe('ion:image-outline');
    expect(iconFor('video')).toBe('ion:play-circle-outline');
    expect(iconFor('')).toBe('ion:file-tray-outline');
  });
});

describe('refusals (hub#1776)', () => {
  it('each code has its own sentence; one nobody knows, the general one', () => {
    expect(refusalKey('base.file_exists')).toBe('base.files.refusal.exists');
    expect(refusalKey('permission_denied')).toBe('base.files.refusal.onlyAdmin');
    expect(refusalKey('network_error')).toBe('base.files.refusal.connection');
    expect(refusalKey('something_new')).toBe('base.files.refusal.generic');
    expect(refusalKey(undefined)).toBe('base.files.refusal.generic');
  });

  it('every code base/files.py and base/services.py write has its sentence, in English and in Spanish', () => {
    const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
    const sources = ['files.py', 'services.py'].map((file) => readFileSync(join(root, file), 'utf8')).join('\n');
    const written = new Set([...sources.matchAll(/code="(base\.file_[a-z_]+)"/g)].map((match) => match[1]));
    expect(written.size).toBeGreaterThan(8);
    for (const code of written) {
      const key = refusalKey(code);
      expect(key, code).not.toBe('base.files.refusal.generic');
    }
    const leaf = (catalogue: Record<string, unknown>, key: string) =>
      key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalogue);
    for (const key of new Set(Object.values(REFUSAL_KEYS))) {
      expect(typeof leaf(en, key), key).toBe('string');
      expect(typeof leaf(es, key), key).toBe('string');
    }
  });
});

// A long name is cut in the middle of what it says, never in its extension (Drive, Dropbox, iOS Files): the screen
// shows the stem with an ellipsis and the extension whole.
describe('splitName', () => {
  it('splits a file name into what it says and its extension', () => {
    expect(splitName('supplier price list for the second quarter.csv')).toEqual({
      stem: 'supplier price list for the second quarter',
      extension: '.csv',
    });
    expect(splitName('notes (1).txt')).toEqual({ stem: 'notes (1)', extension: '.txt' });
    expect(splitName('archive.tar.gz')).toEqual({ stem: 'archive.tar', extension: '.gz' });
  });

  it('a name without an extension is all stem: a dot file, a trailing dot, words after a dot, a folder', () => {
    expect(splitName('.htaccess')).toEqual({ stem: '.htaccess', extension: '' });
    expect(splitName('Invoices 2026')).toEqual({ stem: 'Invoices 2026', extension: '' });
    expect(splitName('report.')).toEqual({ stem: 'report.', extension: '' });
    expect(splitName('v2. final notes')).toEqual({ stem: 'v2. final notes', extension: '' });
    expect(splitName('logo.png', true)).toEqual({ stem: 'logo.png', extension: '' });
  });
});

// A notice is one line of text (Material's snackbar: a short message): a batch that says two things says them as
// sentences one after the other, each ending with its stop, never with a line break the notice paints as a space.
describe('joinSentences', () => {
  it('puts each part after the other as a sentence, on one line', () => {
    const said = joinSentences(['Files uploaded.', 'Could not upload “a.exe”: Programs (.exe) can’t be kept in Files: x']);
    expect(said).toBe('Files uploaded. Could not upload “a.exe”: Programs (.exe) can’t be kept in Files: x.');
    expect(said).not.toMatch(/\n/);
  });

  it('leaves out what is empty and keeps a stop the part already has', () => {
    expect(joinSentences(['', '  Archivos subidos.  ', '¿Seguro?', 'Espera…', ''])).toBe('Archivos subidos. ¿Seguro? Espera…');
    expect(joinSentences(['Line one\nline two'])).toBe('Line one line two.');
    expect(joinSentences([])).toBe('');
  });
});
