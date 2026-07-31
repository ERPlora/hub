// @vitest-environment happy-dom
// Contrato de la capa PURA del visor de /files (sin Vue, sin red, sin parsers pesados):
//   - previewKindFor      → qué visor toca según el fichero (routing de tipos)
//   - decodeText          → bytes a texto (BOM, UTF-8, y cp1252 porque el Excel español
//                           exporta CSV en Windows-1252 y salía con caracteres rotos)
//   - parseDelimited      → CSV/TSV con comillas RFC4180 y delimitador AUTODETECTADO
//                           (el Excel en español usa `;`, no `,`)
//   - sanitizeDocumentHtml→ allowlist sobre el HTML que devuelve mammoth al convertir un .docx:
//                           es contenido de un fichero SUBIDO por un tercero, nunca de confianza.
import { describe, it, expect } from 'vitest';
import {
  previewKindFor,
  mimeTypeFor,
  decodeText,
  parseDelimited,
  sanitizeDocumentHtml,
} from './file-preview';

describe('mimeTypeFor', () => {
  it('da el tipo que necesita el object URL para que <img>/<video> pinten', () => {
    // Un `Blob` sin `type` produce un object URL que el navegador no sabe interpretar.
    expect(mimeTypeFor('logo.png')).toBe('image/png');
    expect(mimeTypeFor('foto.JPG')).toBe('image/jpeg');
    expect(mimeTypeFor('spot.mp4')).toBe('video/mp4');
    expect(mimeTypeFor('aviso.mp3')).toBe('audio/mpeg');
    expect(mimeTypeFor('factura.pdf')).toBe('application/pdf');
  });

  it('cae a binario genérico cuando no lo conoce', () => {
    expect(mimeTypeFor('backup.zzz')).toBe('application/octet-stream');
  });
});

describe('previewKindFor', () => {
  it('enruta las imágenes que un ERP guarda (logos, fotos de producto, escaneos)', () => {
    for (const name of ['logo.png', 'foto.JPG', 'a.jpeg', 'x.webp', 'anim.gif', 'i.bmp', 'n.avif']) {
      expect(previewKindFor(name)).toBe('image');
    }
  });

  it('enruta el PDF, que es el documento más común del ERP', () => {
    expect(previewKindFor('factura-2026-07.pdf')).toBe('pdf');
    expect(previewKindFor('ALBARAN.PDF')).toBe('pdf');
  });

  it('enruta las hojas de cálculo modernas y los delimitados', () => {
    for (const name of ['stock.xlsx', 'macro.xlsm', 'export.csv', 'datos.tsv']) {
      expect(previewKindFor(name)).toBe('sheet');
    }
  });

  it('enruta los documentos de Word modernos', () => {
    expect(previewKindFor('presupuesto.docx')).toBe('doc');
  });

  it('no promete lo que no puede leer: los binarios legados de Office caen a descarga', () => {
    // `.xls` y `.doc` son OLE2 binario; ninguna lib del bundle los lee. Mejor decirlo que
    // pintar un visor vacío.
    expect(previewKindFor('viejo.xls')).toBe('none');
    expect(previewKindFor('viejo.doc')).toBe('none');
  });

  it('enruta el texto plano, los logs y el código', () => {
    for (const name of ['hub.log', 'notas.txt', 'README.md', 'factura.xml', 'q.sql', 'a.yml']) {
      expect(previewKindFor(name)).toBe('text');
    }
  });

  it('separa el JSON del texto plano (tiene visor propio plegable)', () => {
    expect(previewKindFor('module.json')).toBe('json');
  });

  it('enruta audio y vídeo', () => {
    expect(previewKindFor('spot.mp4')).toBe('video');
    expect(previewKindFor('aviso.mp3')).toBe('audio');
  });

  it('cae a "none" cuando no hay nada que enseñar', () => {
    expect(previewKindFor('backup.zip')).toBe('none');
    expect(previewKindFor('sin-extension')).toBe('none');
    expect(previewKindFor('')).toBe('none');
  });

  it('usa el último punto del nombre, no el primero', () => {
    expect(previewKindFor('informe.2026.07.pdf')).toBe('pdf');
  });

  it('prefiere el `ext` que ya calculó el runtime cuando viene informado', () => {
    // El listado de media entrega `ext`; si está, es la fuente (en S3 el nombre puede venir sin él).
    expect(previewKindFor('objeto-sin-ext', 'pdf')).toBe('pdf');
  });
});

describe('decodeText', () => {
  const bytes = (...values: number[]): ArrayBuffer => new Uint8Array(values).buffer;

  it('decodifica UTF-8 con acentos', () => {
    expect(decodeText(new TextEncoder().encode('Café con leche').buffer)).toBe('Café con leche');
  });

  it('se come el BOM en vez de escupirlo como primer carácter', () => {
    const withBom = new Uint8Array([0xef, 0xbb, 0xbf, ...new TextEncoder().encode('Hola')]);
    expect(decodeText(withBom.buffer)).toBe('Hola');
  });

  it('cae a Windows-1252 cuando los bytes no son UTF-8 válido (CSV del Excel español)', () => {
    // 0xF1 = "ñ" en cp1252; en UTF-8 es un byte suelto inválido.
    expect(decodeText(bytes(0x41, 0xf1, 0x6f))).toBe('Año');
  });

  it('entiende el UTF-16 con BOM que exporta el Bloc de notas de Windows', () => {
    expect(decodeText(bytes(0xff, 0xfe, 0x48, 0x00, 0x69, 0x00))).toBe('Hi'); // LE
    expect(decodeText(bytes(0xfe, 0xff, 0x00, 0x48, 0x00, 0x69))).toBe('Hi'); // BE
  });
});

describe('parseDelimited', () => {
  it('parsea un CSV con cabecera y filas', () => {
    expect(parseDelimited('ref,nombre\nA-1,Menú\nA-2,Café')).toEqual([
      ['ref', 'nombre'],
      ['A-1', 'Menú'],
      ['A-2', 'Café'],
    ]);
  });

  it('autodetecta el punto y coma del Excel español', () => {
    expect(parseDelimited('ref;base;total\nA-1;12,00;14,52')).toEqual([
      ['ref', 'base', 'total'],
      ['A-1', '12,00', '14,52'],
    ]);
  });

  it('autodetecta el tabulador', () => {
    expect(parseDelimited('a\tb\n1\t2')).toEqual([
      ['a', 'b'],
      ['1', '2'],
    ]);
  });

  it('respeta el delimitador dentro de comillas', () => {
    expect(parseDelimited('ref,concepto\nA-1,"Menú, del día"')).toEqual([
      ['ref', 'concepto'],
      ['A-1', 'Menú, del día'],
    ]);
  });

  it('entiende la comilla escapada y el salto de línea dentro del campo', () => {
    expect(parseDelimited('a\n"dice ""hola""\ny sigue"')).toEqual([['a'], ['dice "hola"\ny sigue']]);
  });

  it('soporta CRLF y descarta la línea final vacía', () => {
    expect(parseDelimited('a,b\r\n1,2\r\n')).toEqual([
      ['a', 'b'],
      ['1', '2'],
    ]);
  });
});

describe('sanitizeDocumentHtml', () => {
  it('conserva el formato que mammoth produce a partir de un .docx', () => {
    const html = sanitizeDocumentHtml(
      '<h1>Presupuesto</h1><p><strong>Total:</strong> <em>1.200 €</em></p>' +
        '<table><tr><td>Concepto</td></tr></table><ul><li>Uno</li></ul>',
    );
    expect(html).toContain('<h1>Presupuesto</h1>');
    expect(html).toContain('<strong>Total:</strong>');
    expect(html).toContain('<em>1.200 €</em>');
    expect(html).toContain('<td>Concepto</td>');
    expect(html).toContain('<li>Uno</li>');
  });

  it('conserva las imágenes incrustadas del documento (mammoth las trae como data URI)', () => {
    expect(sanitizeDocumentHtml('<img src="data:image/png;base64,iVBOR" alt="sello">')).toContain(
      'data:image/png;base64,iVBOR',
    );
  });

  it('elimina el script incrustado en un .docx malicioso', () => {
    const html = sanitizeDocumentHtml('<p>ok</p><script>fetch("/api/media")</script>');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('fetch(');
    expect(html).toContain('<p>ok</p>');
  });

  it('elimina los manejadores inline y las URLs javascript:', () => {
    const html = sanitizeDocumentHtml('<p onclick="alert(1)">x</p><a href="javascript:alert(1)">y</a>');
    expect(html).not.toContain('onclick');
    expect(html).not.toContain('javascript:');
    expect(html).toContain('x');
    expect(html).toContain('y');
  });

  it('elimina los iframes y objetos (la CSP del Hub Local los prohíbe de todas formas)', () => {
    const html = sanitizeDocumentHtml('<iframe></iframe><object data="x"></object><p>z</p>');
    expect(html).not.toContain('<iframe');
    expect(html).not.toContain('<object');
    expect(html).toContain('<p>z</p>');
  });

  it('no deja que una imagen remota filtre la navegación a un tercero', () => {
    // Un `<img src="https://evil.test/beacon.png">` dentro del docx avisaría al atacante de que
    // el documento se ha abierto (y con qué IP). Solo se permiten data: URIs.
    expect(sanitizeDocumentHtml('<img src="https://evil.test/beacon.png">')).not.toContain(
      'evil.test',
    );
  });
});
