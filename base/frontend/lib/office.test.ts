// Files › the preview of a spreadsheet (.xlsx) and of a Word document (.docx) (hub#578, BASE-F74): read in the page's
// own thread with maintained libraries, loaded only when such a file opens. Under the Hub's production CSP (a nonce
// and 'strict-dynamic', no 'unsafe-eval') and Trusted Types (the `default` policy lets only an icon's SVG through as
// HTML and no script URL but the allowed origins'), nothing may start a Worker from a blob, parse HTML with the
// browser, write `innerHTML` or evaluate code: each test below runs the readers with those doors trapped. A document
// arrives as a tree of the few elements a preview needs, never as HTML to paint.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { strToU8, unzipSync, zipSync } from 'fflate';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { PreviewTooLarge } from './files';
import { type DocumentNode, documentNodes, readDocument, readSheets } from './office';

/** What `read-excel-file` is handed, each time: the library itself, otherwise. */
const handed = vi.hoisted(() => [] as ArrayBuffer[]);
vi.mock('read-excel-file/universal', async (importOriginal) => {
  const real = await importOriginal<typeof import('read-excel-file/universal')>();
  return {
    ...real,
    default: (input: ArrayBuffer, options?: Parameters<typeof real.default>[1]) => {
      handed.push(input);
      return real.default(input, options);
    },
  };
});

/** The parts of the zip `data` as its directory lists them (nothing unpacked). */
function partsOf(data: ArrayBuffer | Uint8Array): { name: string; compression: number; originalSize: number }[] {
  const found: { name: string; compression: number; originalSize: number }[] = [];
  unzipSync(new Uint8Array(data), {
    filter: ({ name, compression, originalSize }) => {
      found.push({ name, compression, originalSize });
      return false;
    },
  });
  return found;
}

const FILES = join(dirname(fileURLToPath(import.meta.url)), '..', '__tests__', 'files');
const fixture = (name: string) => new Uint8Array(readFileSync(join(FILES, name)));

const XML = '<?xml version="1.0" encoding="UTF-8"?>';
const RELS = 'http://schemas.openxmlformats.org/package/2006/relationships';
const OFFICE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';

/** A real .xlsx built here: one sheet, «Grande», of `rows` rows (a name and a number each). Past some 3,000 rows its
 *  sheet weighs more than 512 KB unpacked, where fflate's asynchronous unzip hands the work to a Worker. */
function workbook(rows: number): Uint8Array {
  const cells = Array.from(
    { length: rows },
    (_, i) => `<row r="${i + 1}"><c r="A${i + 1}" t="inlineStr"><is><t>Producto ${i + 1}</t></is></c><c r="B${i + 1}"><v>${i}</v></c></row>`,
  ).join('');
  return zipSync({
    '[Content_Types].xml': strToU8(
      `${XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`,
    ),
    '_rels/.rels': strToU8(`${XML}<Relationships xmlns="${RELS}"><Relationship Id="rId1" Type="${OFFICE}/officeDocument" Target="xl/workbook.xml"/></Relationships>`),
    'xl/workbook.xml': strToU8(
      `${XML}<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="${OFFICE}"><sheets><sheet name="Grande" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    ),
    'xl/_rels/workbook.xml.rels': strToU8(
      `${XML}<Relationships xmlns="${RELS}"><Relationship Id="rId1" Type="${OFFICE}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`,
    ),
    'xl/worksheets/sheet1.xml': strToU8(
      `${XML}<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${cells}</sheetData></worksheet>`,
    ),
  });
}

/** Every door the production CSP and Trusted Types keep shut, each one recording its caller and refusing, as the
 *  browser does there. `restore` puts the real ones back. */
function trapSinks() {
  const hits: string[] = [];
  const undo: (() => void)[] = [];
  const refuse = (door: string) => {
    hits.push(door);
    throw new TypeError(`refused by the CSP: ${door}`);
  };
  const replace = (target: object, key: string, descriptor: PropertyDescriptor) => {
    const own = Object.getOwnPropertyDescriptor(target, key);
    Object.defineProperty(target, key, { configurable: true, ...descriptor });
    undo.push(() => (own ? Object.defineProperty(target, key, own) : Reflect.deleteProperty(target, key)));
  };
  replace(globalThis, 'Worker', {
    writable: true,
    value: class {
      constructor() {
        refuse('Worker');
      }
    },
  });
  replace(DOMParser.prototype, 'parseFromString', { writable: true, value: () => refuse('DOMParser.parseFromString') });
  const html = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
  replace(Element.prototype, 'innerHTML', { get: html?.get, set: () => refuse('innerHTML') });
  replace(Element.prototype, 'insertAdjacentHTML', { writable: true, value: () => refuse('insertAdjacentHTML') });
  replace(globalThis, 'eval', { writable: true, value: () => refuse('eval') });
  replace(globalThis, 'Function', {
    writable: true,
    value: new Proxy(Function, { apply: () => refuse('Function'), construct: () => refuse('Function') }),
  });
  return { hits, restore: () => undo.reverse().forEach((step) => step()) };
}

let trap: ReturnType<typeof trapSinks> | null = null;
const trapped = () => (trap = trapSinks());

beforeAll(async () => {
  // Loaded once with every door open, as the page loads a chunk: the trap is about what reading a file does.
  await Promise.all([import('fflate'), import('read-excel-file/universal'), import('mammoth'), import('htmlparser2')]);
});

afterEach(() => {
  trap?.restore();
  trap = null;
});

function textOf(nodes: readonly DocumentNode[]): string {
  return nodes.map((node) => (typeof node === 'string' ? node : textOf(node.children))).join('');
}

function tagsOf(nodes: readonly DocumentNode[]): string[] {
  return nodes.flatMap((node) => (typeof node === 'string' ? [] : [node.tag, ...tagsOf(node.children)]));
}

describe('a spreadsheet', () => {
  it('reads every sheet of a real .xlsx with its name, its texts, numbers and dates', async () => {
    const sheets = await readSheets(fixture('sample.xlsx'));
    expect(sheets.map((sheet) => sheet.name)).toEqual(['Ventas', 'Notas']);
    expect(sheets[0].rows).toEqual([
      ['Producto', 'Precio', 'Fecha', 'Pagado'],
      ['Café solo', 1.2, new Date('2026-11-03T00:00:00Z'), 1],
      ['Tostada', 2.5, new Date('2026-11-04T00:00:00Z'), 0],
    ]);
    expect(sheets[1].rows).toEqual([['Cerrar la caja a las 23:00']]);
  });

  it('reads a big sheet in the page’s own thread: it hands the library the parts stored, never compressed', async () => {
    // fflate's unzip (the library's) hands a compressed part over 512 KB to a Worker started from a blob, which the
    // production CSP refuses; this file's sheet is one (deflated, 1.5 MB unpacked).
    const big = workbook(30_000);
    expect(partsOf(big).find((part) => part.name === 'xl/worksheets/sheet1.xml')).toMatchObject({ compression: 8 });
    expect(partsOf(big).find((part) => part.name === 'xl/worksheets/sheet1.xml')?.originalSize).toBeGreaterThan(512 * 1024);
    trapped();
    const sheets = await readSheets(big);
    expect(trap?.hits).toEqual([]);
    expect(partsOf(handed[handed.length - 1]).map((part) => part.compression)).toEqual([0, 0, 0, 0, 0]);
    expect(sheets[0].name).toBe('Grande');
    expect(sheets[0].rows).toHaveLength(30_000);
    expect(sheets[0].rows[29_999]).toEqual(['Producto 30000', 29_999]);
  });

  it('a file that is no spreadsheet (damaged, or another one renamed) is refused, and is not «too large»', async () => {
    await expect(readSheets(new Uint8Array([80, 75, 3, 4, 1, 2, 3]))).rejects.not.toBeInstanceOf(PreviewTooLarge);
    await expect(readSheets(new Uint8Array([1, 2, 3]))).rejects.toThrow();
    await expect(readSheets(fixture('sample.docx'))).rejects.not.toBeInstanceOf(PreviewTooLarge);
  });

  it('one that unpacks to more than the preview reads is «too large» before a cell is read', async () => {
    await expect(readSheets(fixture('sample.xlsx'), 1_000)).rejects.toBeInstanceOf(PreviewTooLarge);
  });
});

describe('the elements of a document', () => {
  it('keeps the formatting a preview shows: headings, bold, italics, lists, tables', async () => {
    const nodes = await documentNodes(
      '<h1>Informe</h1><p>Con <strong>fuerza</strong>, <em>cada día</em>, <u>subrayado</u> y <s>tachado</s>.</p>' +
        '<ul><li>Uno</li></ul><ol><li>Dos</li></ol><table><tr><td colspan="2"><p>Celda</p></td></tr></table>',
    );
    expect(nodes[0]).toEqual({ tag: 'h1', attrs: {}, children: ['Informe'] });
    expect(nodes[1]).toEqual({
      tag: 'p',
      attrs: {},
      children: [
        'Con ',
        { tag: 'strong', attrs: {}, children: ['fuerza'] },
        ', ',
        { tag: 'em', attrs: {}, children: ['cada día'] },
        ', ',
        { tag: 'u', attrs: {}, children: ['subrayado'] },
        ' y ',
        { tag: 's', attrs: {}, children: ['tachado'] },
        '.',
      ],
    });
    expect(tagsOf(nodes.slice(2))).toEqual(['ul', 'li', 'ol', 'li', 'table', 'tr', 'td', 'p']);
    expect((nodes[4] as { children: { children: { attrs: object }[] }[] }).children[0].children[0].attrs).toEqual({ colspan: '2' });
  });

  it('never keeps a script, a style, a frame or an event handler: they are not elements of a document', async () => {
    const nodes = await documentNodes(
      '<p>a<script>alert(1)</script><style>p{}</style><iframe src="x"></iframe><svg><text>s</text></svg>' +
        '<img src="x" onerror="alert(2)"><b onclick="alert(3)" style="color:red" class="x" id="y">b</b></p>' +
        '<object data="x">o</object><template><p>t</p></template><noscript>n</noscript>',
    );
    expect(nodes).toEqual([{ tag: 'p', attrs: {}, children: ['a', { tag: 'b', attrs: {}, children: ['b'] }] }]);
  });

  it('a link only to the web or to an email; any other keeps its words and loses its address', async () => {
    const nodes = await documentNodes(
      '<p><a href="javascript:alert(1)">trampa</a> <a href=" JaVaScRiPt:alert(1)">otra</a> <a href="#footnote-1">nota</a> ' +
        '<a href="https://erplora.com/" target="_top" onclick="x">web</a> <a href="mailto:hola@erplora.com">correo</a></p>',
    );
    expect(nodes).toEqual([
      {
        tag: 'p',
        attrs: {},
        children: [
          'trampa',
          ' ',
          'otra',
          ' ',
          'nota',
          ' ',
          { tag: 'a', attrs: { href: 'https://erplora.com/' }, children: ['web'] },
          ' ',
          { tag: 'a', attrs: { href: 'mailto:hola@erplora.com' }, children: ['correo'] },
        ],
      },
    ]);
  });

  it('an image only from inside the document (a data URL of a raster image), never from an address or an SVG', async () => {
    const nodes = await documentNodes(
      '<p><img src="data:image/png;base64,iVBORw0KGgo=" alt="logo" onerror="x">' +
        '<img src="https://tracker.test/pixel.png"><img src="data:image/svg+xml;base64,PHN2Zz4="></p>',
    );
    expect(nodes).toEqual([
      { tag: 'p', attrs: {}, children: [{ tag: 'img', attrs: { src: 'data:image/png;base64,iVBORw0KGgo=', alt: 'logo' }, children: [] }] },
    ]);
  });

  it('a text that looks like markup stays a text', async () => {
    expect(await documentNodes('<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>')).toEqual([
      { tag: 'p', attrs: {}, children: ['<script>alert(1)</script>'] },
    ]);
  });
});

describe('a Word document', () => {
  it('reads a real .docx into its elements, with nothing the CSP refuses', async () => {
    trapped();
    const nodes = await readDocument(fixture('sample.docx'));
    expect(trap?.hits).toEqual([]);
    expect(nodes[0]).toEqual({ tag: 'h1', attrs: {}, children: ['Informe de noviembre'] });
    expect(tagsOf(nodes)).toEqual(expect.arrayContaining(['h2', 'strong', 'em', 'ul', 'ol', 'li', 'table', 'td', 'a']));
    expect(tagsOf(nodes)).not.toContain('script');
    // Its text that looks like markup is text; its `javascript:` link keeps only its words.
    expect(textOf(nodes)).toContain('<script>alert(1)</script> y <img src=x onerror=alert(2)>');
    expect(textOf(nodes)).toContain('Enlace trampa y la web de ERPlora.');
    expect(JSON.stringify(nodes)).not.toContain('javascript:');
    expect(JSON.stringify(nodes)).toContain('"href":"https://erplora.com/"');
  });

  it('a file that is no Word document is refused; one that unpacks to too much is «too large»', async () => {
    await expect(readDocument(new Uint8Array([1, 2, 3]))).rejects.toThrow();
    await expect(readDocument(fixture('sample.xlsx'))).rejects.not.toBeInstanceOf(PreviewTooLarge);
    await expect(readDocument(fixture('sample.docx'), 1_000)).rejects.toBeInstanceOf(PreviewTooLarge);
  });
});
