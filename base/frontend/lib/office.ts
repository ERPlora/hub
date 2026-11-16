// Files › the preview of a spreadsheet (.xlsx, .xlsm) and of a Word document (.docx) (hub#578, BASE-F74; the old
// hub's `file-preview-loaders.ts`): read with maintained libraries, `read-excel-file` and `mammoth`, imported only
// when such a file opens (their chunks never weigh on the start), from the bytes the SDK fetched (they fetch nothing).
//
// Everything runs in the page's own thread, as pdf.js does (`pdf.ts`): under the production CSP (a nonce and
// 'strict-dynamic') and Trusted Types (`@erplora/ui/shell`'s `default` policy refuses every script URL but the allowed
// origins'), a Worker started from a blob is refused, and fflate's asynchronous unzip (the one both libraries use)
// starts one for any part over 512 KB. So the zip is unpacked here, synchronously, and handed over stored (no
// compression), which they read without one. Unpacking here also caps what it unpacks to (`OFFICE_UNPACKED_MAX_BYTES`):
// a zip bomb is «too large» before a cell is read.
//
// A Word document becomes a tree of the few elements a preview shows (`DocumentNode`), never HTML: `mammoth` writes
// HTML, `htmlparser2` reads it in plain JavaScript (the browser's `DOMParser` and `innerHTML` are Trusted Types sinks
// the policy refuses), and only what a document's formatting needs is kept; `FileDocument.vue` draws it element by
// element. A script, a style, a frame, an event handler, a `javascript:` link or an image from an address never makes
// it into the tree.
import { OFFICE_UNPACKED_MAX_BYTES, PreviewTooLarge, type SheetCell } from './files';

/** A sheet of a spreadsheet: its name and its rows, as the cells come (`cellText` writes them). */
export interface Sheet {
  name: string;
  rows: SheetCell[][];
}

/** The elements a document keeps. */
export type DocumentTag =
  | 'p' | 'br' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'strong' | 'b' | 'em' | 'i' | 'u' | 's' | 'sub' | 'sup'
  | 'ul' | 'ol' | 'li' | 'blockquote' | 'table' | 'thead' | 'tbody' | 'tr' | 'td' | 'th' | 'a' | 'img';

/** A text, or an element with only the attributes it may keep: `href` of a link, `src` and `alt` of an image,
 *  `colspan` and `rowspan` of a cell. */
export type DocumentNode = string | { tag: DocumentTag; attrs: Readonly<Record<string, string>>; children: DocumentNode[] };

const KEPT: ReadonlySet<string> = new Set<DocumentTag>([
  'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b', 'em', 'i', 'u', 's', 'sub', 'sup',
  'ul', 'ol', 'li', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'a', 'img',
]);
/** Gone with all they hold: none of them is a document's text. Any other element not kept leaves its text. */
const DROPPED: ReadonlySet<string> = new Set([
  'script', 'style', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet', 'svg', 'math', 'template',
  'noscript', 'title', 'head', 'meta', 'link', 'base', 'form', 'input', 'button', 'select', 'textarea', 'option',
  'canvas', 'audio', 'video', 'source', 'track',
]);
/** A link only to the web or to an email; any other keeps its words. */
const LINK = /^(?:https?:|mailto:)/i;
/** An image only from inside the document: a raster one as a data URL (never an address, that tells its sender the
 *  file was opened, nor an SVG). */
const IMAGE = /^data:image\/(?:png|jpe?g|gif|webp|bmp);base64,[\w+/=\s]*$/i;
const SPAN = /^[1-9]\d{0,2}$/;

/** The parts of the zip `data` that `wanted` names, unpacked here and stored again without compression; refused as
 *  `PreviewTooLarge` past `maxUnpacked` bytes. */
async function repack(data: Uint8Array, wanted: (name: string) => boolean, maxUnpacked: number): Promise<ArrayBuffer> {
  const { unzipSync, zipSync } = await import('fflate');
  let unpacked = 0;
  const parts = unzipSync(data, {
    filter: (part) => {
      if (!wanted(part.name)) return false;
      unpacked += part.originalSize;
      if (unpacked > maxUnpacked) throw new PreviewTooLarge();
      return true;
    },
  });
  const stored = zipSync(parts, { level: 0 });
  return stored.buffer.slice(stored.byteOffset, stored.byteOffset + stored.byteLength) as ArrayBuffer;
}

/** Every sheet of the spreadsheet `data`, in order. Refused when it is no spreadsheet (damaged, or another file). */
export async function readSheets(data: Uint8Array, maxUnpacked = OFFICE_UNPACKED_MAX_BYTES): Promise<Sheet[]> {
  const stored = await repack(data, (name) => /\.(?:xml|rels)$/i.test(name), maxUnpacked);
  const { default: readXlsxFile } = await import('read-excel-file/universal');
  const sheets = await readXlsxFile(stored);
  return sheets.map(({ sheet, data: rows }) => ({ name: sheet, rows: rows as unknown as SheetCell[][] }));
}

/** The Word document `data` as the elements a preview shows. Refused when it is no Word document. */
export async function readDocument(data: Uint8Array, maxUnpacked = OFFICE_UNPACKED_MAX_BYTES): Promise<DocumentNode[]> {
  const stored = await repack(data, () => true, maxUnpacked);
  const { default: mammoth } = await import('mammoth');
  // The browser build of mammoth reads `arrayBuffer`; its Node one (the tests'), `buffer`.
  const input = { arrayBuffer: stored, buffer: stored } as unknown as { arrayBuffer: ArrayBuffer };
  const { value } = await mammoth.convertToHtml(input);
  return documentNodes(value);
}

/** The HTML `html` (mammoth's) as the elements a document keeps, read without the browser's parser. */
export async function documentNodes(html: string): Promise<DocumentNode[]> {
  const { parseDocument, ElementType } = await import('htmlparser2');
  type Node = ReturnType<typeof parseDocument>['children'][number];
  type Element = { name: string; attribs: Record<string, string | undefined>; children: Node[] };

  const keep = (nodes: readonly Node[]): DocumentNode[] =>
    nodes.flatMap((node): DocumentNode[] => {
      if (node.type === ElementType.Text) {
        const text = (node as { data: string }).data;
        return text ? [text] : [];
      }
      // Comments, CDATA and declarations are no text of the document.
      if (!ElementType.isTag(node)) return [];
      const element = node as unknown as Element;
      const tag = element.name.toLowerCase();
      if (DROPPED.has(tag)) return [];
      const children = keep(element.children);
      if (!KEPT.has(tag)) return children;
      const kept = tag as DocumentTag;
      const attrs = element.attribs;
      if (kept === 'a') {
        const href = (attrs.href ?? '').trim();
        return LINK.test(href) ? [{ tag: kept, attrs: { href }, children }] : children;
      }
      if (kept === 'img') {
        const src = (attrs.src ?? '').trim();
        if (!IMAGE.test(src)) return [];
        return [{ tag: kept, attrs: attrs.alt ? { src, alt: attrs.alt } : { src }, children: [] }];
      }
      if (kept === 'td' || kept === 'th') {
        const spans: Record<string, string> = {};
        for (const name of ['colspan', 'rowspan']) {
          const span = attrs[name];
          if (span && SPAN.test(span)) spans[name] = span;
        }
        return [{ tag: kept, attrs: spans, children }];
      }
      return [{ tag: kept, attrs: {}, children }];
    });

  return keep(parseDocument(html).children);
}
