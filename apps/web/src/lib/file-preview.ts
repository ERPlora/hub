// Capa PURA del visor de ficheros de `/files`: decide QUÉ visor toca y prepara el contenido.
// No toca la red ni Vue ni los parsers pesados (pdf.js / xlsx / docx) — esos se cargan
// perezosamente en `FilePreviewModal.vue`, solo cuando abres un fichero de ese tipo.
//
// Por qué existe este módulo aparte: el routing de tipos, la decodificación de texto, el CSV y
// el saneado del HTML de Word son reglas de negocio con casos límite reales (cp1252, `;` del
// Excel español, un .docx con script dentro) y merecen tests propios sin montar un modal.

/** Visor que corresponde a un fichero. `none` = no hay previsualización, solo descarga. */
export type PreviewKind =
  | 'image'
  | 'pdf'
  | 'sheet'
  | 'doc'
  | 'text'
  | 'json'
  | 'video'
  | 'audio'
  | 'none';

// Extensiones por visor. Solo se declara lo que REALMENTE se sabe pintar: prometer un visor y
// enseñar un hueco es peor que ofrecer la descarga.
const BY_EXTENSION: Record<string, PreviewKind> = {
  // Imágenes (el `<img>` no ejecuta scripts, tampoco dentro de un SVG).
  png: 'image',
  jpg: 'image',
  jpeg: 'image',
  webp: 'image',
  gif: 'image',
  bmp: 'image',
  avif: 'image',
  svg: 'image',
  ico: 'image',
  // Documento estrella del ERP.
  pdf: 'pdf',
  // Hojas de cálculo: OOXML + delimitados. `.xls` (OLE2 binario) NO — ver nota abajo.
  xlsx: 'sheet',
  xlsm: 'sheet',
  csv: 'sheet',
  tsv: 'sheet',
  // Word moderno (OOXML). `.doc` (OLE2 binario) NO.
  docx: 'doc',
  // Texto plano, registros y código.
  txt: 'text',
  log: 'text',
  md: 'text',
  xml: 'text',
  yml: 'text',
  yaml: 'text',
  ini: 'text',
  conf: 'text',
  sql: 'text',
  html: 'text',
  css: 'text',
  js: 'text',
  ts: 'text',
  rs: 'text',
  py: 'text',
  sh: 'text',
  // JSON tiene visor plegable propio.
  json: 'json',
  // Multimedia.
  mp4: 'video',
  webm: 'video',
  ogv: 'video',
  mov: 'video',
  mp3: 'audio',
  wav: 'audio',
  ogg: 'audio',
  m4a: 'audio',
  flac: 'audio',
};

/** Extensión normalizada (minúsculas, sin punto). Cadena vacía si el nombre no tiene. */
export function extensionOf(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? '';
  const dot = base.lastIndexOf('.');
  return dot > 0 ? base.slice(dot + 1).toLowerCase() : '';
}

/**
 * Visor que corresponde al fichero. `ext` es el que ya calculó el runtime en el listado de media
 * (en S3 la clave puede no llevar extensión en el nombre visible); si viene, manda.
 */
export function previewKindFor(name: string, ext?: string): PreviewKind {
  const key = (ext ?? '').trim().toLowerCase().replace(/^\./, '') || extensionOf(name);
  return BY_EXTENSION[key] ?? 'none';
}

// MIME por extensión. Solo hace falta para los tipos que se pintan desde un object URL
// (`<img>`, `<video>`, `<audio>`): un Blob sin `type` da una URL que el navegador no interpreta.
const MIME_BY_EXTENSION: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  gif: 'image/gif',
  bmp: 'image/bmp',
  avif: 'image/avif',
  svg: 'image/svg+xml',
  ico: 'image/x-icon',
  pdf: 'application/pdf',
  mp4: 'video/mp4',
  webm: 'video/webm',
  ogv: 'video/ogg',
  mov: 'video/quicktime',
  mp3: 'audio/mpeg',
  wav: 'audio/wav',
  ogg: 'audio/ogg',
  m4a: 'audio/mp4',
  flac: 'audio/flac',
};

/** Tipo MIME del fichero, o binario genérico si no se conoce. */
export function mimeTypeFor(name: string, ext?: string): string {
  const key = (ext ?? '').trim().toLowerCase().replace(/^\./, '') || extensionOf(name);
  return MIME_BY_EXTENSION[key] ?? 'application/octet-stream';
}

/**
 * Bytes → texto. Un ERP guarda logs y CSV generados por Windows: el Excel en español exporta en
 * **Windows-1252**, no en UTF-8, y decodificarlo como UTF-8 llena la pantalla de "�".
 * Orden: BOM UTF-16 → BOM UTF-8 → UTF-8 estricto → cp1252.
 */
export function decodeText(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  if (bytes[0] === 0xff && bytes[1] === 0xfe) {
    return new TextDecoder('utf-16le').decode(bytes.subarray(2));
  }
  if (bytes[0] === 0xfe && bytes[1] === 0xff) {
    return new TextDecoder('utf-16be').decode(bytes.subarray(2));
  }
  const body = bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf ? bytes.subarray(3) : bytes;
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(body);
  } catch {
    return new TextDecoder('windows-1252').decode(body);
  }
}

const DELIMITERS = [',', ';', '\t', '|'] as const;

/** Delimitador más frecuente FUERA de comillas en la primera línea de datos. */
function detectDelimiter(text: string): string {
  const counts = new Map<string, number>(DELIMITERS.map((d) => [d, 0]));
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '"') {
      quoted = !quoted;
    } else if (!quoted && char === '\n') {
      break; // basta la primera línea real (la cabecera)
    } else if (!quoted && counts.has(char)) {
      counts.set(char, (counts.get(char) ?? 0) + 1);
    }
  }
  let best = ',';
  let bestCount = 0;
  for (const [delimiter, count] of counts) {
    if (count > bestCount) {
      best = delimiter;
      bestCount = count;
    }
  }
  return best;
}

/**
 * CSV/TSV → matriz de celdas. Comillas RFC 4180 (`""` escapa una comilla, y dentro de comillas el
 * delimitador y el salto de línea son literales), CRLF, y delimitador autodetectado — el Excel en
 * español usa `;` porque la coma es el separador decimal.
 */
export function parseDelimited(text: string): string[][] {
  const delimiter = detectDelimiter(text);
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"') {
      quoted = true;
    } else if (char === delimiter) {
      row.push(field);
      field = '';
    } else if (char === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else if (char !== '\r') {
      field += char;
    }
  }
  row.push(field);
  rows.push(row);

  // Un fichero bien formado acaba en salto de línea → última fila vacía que no es un dato.
  while (rows.length && rows[rows.length - 1].every((cell) => cell === '')) rows.pop();
  return rows;
}

// Allowlist del HTML que mammoth genera a partir de un .docx. Todo lo que no esté aquí se cae.
const ALLOWED_TAGS = new Set([
  'p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'strong', 'b', 'em', 'i', 'u', 's', 'sub', 'sup', 'span', 'div',
  'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th',
  'a', 'img',
]);

// Elementos que se borran ENTEROS (con su contenido); el resto de los no permitidos se "desenvuelve"
// conservando el texto, para no perder párrafos por una etiqueta rara.
const DROPPED_TAGS = new Set(['script', 'style', 'iframe', 'object', 'embed', 'link', 'meta', 'svg', 'math', 'form', 'input', 'button']);

const ALLOWED_ATTRS = new Set(['href', 'src', 'alt', 'title', 'colspan', 'rowspan']);

/**
 * Sanea el HTML de un documento SUBIDO (salida de mammoth para un .docx). Es contenido de un
 * tercero: se pinta con `v-html`, así que pasa por allowlist de etiquetas y atributos.
 * - `href` solo http(s)/mailto; nunca `javascript:`.
 * - `src` solo `data:image/…` — una imagen remota dentro del documento sería una baliza que
 *   avisa al atacante (con IP) de que se ha abierto el fichero.
 * - Se borran todos los `on*`.
 */
export function sanitizeDocumentHtml(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html');

  for (const element of Array.from(doc.body.querySelectorAll('*'))) {
    const tag = element.tagName.toLowerCase();
    if (DROPPED_TAGS.has(tag)) {
      element.remove();
      continue;
    }
    if (!ALLOWED_TAGS.has(tag)) {
      element.replaceWith(...Array.from(element.childNodes));
      continue;
    }
    for (const attr of Array.from(element.attributes)) {
      const name = attr.name.toLowerCase();
      if (!ALLOWED_ATTRS.has(name)) {
        element.removeAttribute(attr.name);
        continue;
      }
      const value = attr.value.trim();
      if (name === 'href' && !/^(https?:|mailto:|#)/i.test(value)) {
        element.removeAttribute(attr.name);
      }
      if (name === 'src' && !/^data:image\//i.test(value)) {
        element.remove();
      }
    }
  }
  return doc.body.innerHTML;
}
