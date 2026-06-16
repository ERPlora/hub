import { LitElement, html, css, svg, type SVGTemplateResult } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-qr — generador de código QR EN JS PURO (sin dependencias externas) renderizado como SVG.
//
// CSP-SAFE: no usa `eval` ni `new Function`. Toda la codificación es aritmética de bits +
// Reed-Solomon sobre GF(256) implementada a mano; la matriz se pinta como <rect> dentro de un
// <svg> autocontenido en el Shadow DOM (nítido a cualquier tamaño).
//
// ALCANCE: implementación COMPLETA en modo BYTE (UTF-8) con los cuatro niveles de corrección de
// errores (L/M/Q/H) y SELECCIÓN AUTOMÁTICA DE MÁSCARA (las 8 máscaras + reglas de penalización).
// Versiones soportadas: 1–40 (capacidad máxima del estándar). Se elige automáticamente la versión
// más pequeña que quepa para el `value` + nivel EC dados. Modo byte cubre texto/URLs típicas; no se
// implementan los modos numérico/alfanumérico/kanji (no aportan a URLs) ni ECI explícito (los
// bytes UTF-8 se emiten directamente, que es lo que leen los lectores modernos).
//
// API:
//   • prop `value`      → string a codificar (texto/URL). Si vacío, no pinta nada.
//   • prop `ec`         → 'L' | 'M' | 'Q' | 'H' (def 'M'): nivel de corrección de errores.
//   • prop `size`       → px del lado del SVG (def 160).
//   • prop `color`      → color de los módulos "negros" (def var(--ok-text) → #000).
//   • prop `background` → color de fondo (def transparent / var(--ok-surface)).
//   • prop `margin`     → módulos de quiet zone alrededor (def 4, el mínimo del estándar).
//
// Si `value` excede la capacidad de la versión 40 con el EC pedido, se omite el render (no rompe).

// ───────────────────────── Aritmética de Galois Field GF(256) ─────────────────────────
// Polinomio generador 0x11D (x^8 + x^4 + x^3 + x^2 + 1), base estándar de QR.
const GF_EXP = new Uint8Array(512);
const GF_LOG = new Uint8Array(256);
(() => {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    GF_EXP[i] = x;
    GF_LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i++) GF_EXP[i] = GF_EXP[i - 255];
})();

function gfMul(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return GF_EXP[GF_LOG[a] + GF_LOG[b]];
}

// Polinomio generador de Reed-Solomon para `degree` símbolos de corrección.
function rsGeneratorPoly(degree: number): Uint8Array {
  let poly = new Uint8Array([1]);
  for (let i = 0; i < degree; i++) {
    const next = new Uint8Array(poly.length + 1);
    for (let j = 0; j < poly.length; j++) {
      next[j] ^= poly[j];
      next[j + 1] ^= gfMul(poly[j], GF_EXP[i]);
    }
    poly = next;
  }
  return poly;
}

// Calcula los `degree` bytes de corrección (resto de la división polinómica) de un bloque de datos.
function rsEncode(data: Uint8Array, degree: number): Uint8Array {
  const gen = rsGeneratorPoly(degree);
  const res = new Uint8Array(data.length + degree);
  res.set(data);
  for (let i = 0; i < data.length; i++) {
    const coef = res[i];
    if (coef !== 0) {
      for (let j = 0; j < gen.length; j++) {
        res[i + j] ^= gfMul(gen[j], coef);
      }
    }
  }
  return res.slice(data.length);
}

// ───────────────────────── Tablas del estándar QR ─────────────────────────
type EcLevel = 'L' | 'M' | 'Q' | 'H';
const EC_ORDER: EcLevel[] = ['L', 'M', 'Q', 'H'];

// Nº total de codewords (datos + EC) por versión (índice = versión − 1).
const TOTAL_CODEWORDS = [
  26, 44, 70, 100, 134, 172, 196, 242, 292, 346, 404, 466, 532, 581, 655, 733, 815, 901, 991, 1085,
  1156, 1258, 1364, 1474, 1588, 1706, 1828, 1921, 2051, 2185, 2323, 2465, 2611, 2761, 2876, 3034,
  3196, 3362, 3532, 3706,
];

// Por [versión-1][EC index] → [ecCodewordsPerBlock, numBlocksGroup1, dataCwGroup1,
// numBlocksGroup2, dataCwGroup2]. Tabla oficial ISO/IEC 18004.
// Orden de EC index: L=0, M=1, Q=2, H=3.
// prettier-ignore
const EC_BLOCKS: number[][][] = [
  /* v1 */[[7,1,19,0,0],[10,1,16,0,0],[13,1,13,0,0],[17,1,9,0,0]],
  /* v2 */[[10,1,34,0,0],[16,1,28,0,0],[22,1,22,0,0],[28,1,16,0,0]],
  /* v3 */[[15,1,55,0,0],[26,1,44,0,0],[18,2,17,0,0],[22,2,13,0,0]],
  /* v4 */[[20,1,80,0,0],[18,2,32,0,0],[26,2,24,0,0],[16,4,9,0,0]],
  /* v5 */[[26,1,108,0,0],[24,2,43,0,0],[18,2,15,2,16],[22,2,11,2,12]],
  /* v6 */[[18,2,68,0,0],[16,4,27,0,0],[24,4,19,0,0],[28,4,15,0,0]],
  /* v7 */[[20,2,78,0,0],[18,4,31,0,0],[18,2,14,4,15],[26,4,13,1,14]],
  /* v8 */[[24,2,97,0,0],[22,2,38,2,39],[22,4,18,2,19],[26,4,14,2,15]],
  /* v9 */[[30,2,116,0,0],[22,3,36,2,37],[20,4,16,4,17],[24,4,12,4,13]],
  /* v10 */[[18,2,68,2,69],[26,4,43,1,44],[24,6,19,2,20],[28,6,15,2,16]],
  /* v11 */[[20,4,81,0,0],[30,1,50,4,51],[28,4,22,4,23],[24,3,12,8,13]],
  /* v12 */[[24,2,92,2,93],[22,6,36,2,37],[26,4,20,6,21],[28,7,14,4,15]],
  /* v13 */[[26,4,107,0,0],[22,8,37,1,38],[24,8,20,4,21],[22,12,11,4,12]],
  /* v14 */[[30,3,115,1,116],[24,4,40,5,41],[20,11,16,5,17],[24,11,12,5,13]],
  /* v15 */[[22,5,87,1,88],[24,5,41,5,42],[30,5,24,7,25],[24,11,12,7,13]],
  /* v16 */[[24,5,98,1,99],[28,7,45,3,46],[24,15,19,2,20],[30,3,15,13,16]],
  /* v17 */[[28,1,107,5,108],[28,10,46,1,47],[28,1,22,15,23],[28,2,14,17,15]],
  /* v18 */[[30,5,120,1,121],[26,9,43,4,44],[28,17,22,1,23],[28,2,14,19,15]],
  /* v19 */[[28,3,113,4,114],[26,3,44,11,45],[26,17,21,4,22],[26,9,13,16,14]],
  /* v20 */[[28,3,107,5,108],[26,3,41,13,42],[30,15,24,5,25],[28,15,15,10,16]],
  /* v21 */[[28,4,116,4,117],[26,17,42,0,0],[28,17,22,6,23],[30,19,16,6,17]],
  /* v22 */[[28,2,111,7,112],[28,17,46,0,0],[30,7,24,16,25],[24,34,13,0,0]],
  /* v23 */[[30,4,121,5,122],[28,4,47,14,48],[30,11,24,14,25],[30,16,15,14,16]],
  /* v24 */[[30,6,117,4,118],[28,6,45,14,46],[30,11,24,16,25],[30,30,16,2,17]],
  /* v25 */[[26,8,106,4,107],[28,8,47,13,48],[30,7,24,22,25],[30,22,15,13,16]],
  /* v26 */[[28,10,114,2,115],[28,19,46,4,47],[28,28,22,6,23],[30,33,16,4,17]],
  /* v27 */[[30,8,122,4,123],[28,22,45,3,46],[30,8,23,26,24],[30,12,15,28,16]],
  /* v28 */[[30,3,117,10,118],[28,3,45,23,46],[30,4,24,31,25],[30,11,15,31,16]],
  /* v29 */[[30,7,116,7,117],[28,21,45,7,46],[30,1,23,37,24],[30,19,15,26,16]],
  /* v30 */[[30,5,115,10,116],[28,19,47,10,48],[30,15,24,25,25],[30,23,15,25,16]],
  /* v31 */[[30,13,115,3,116],[28,2,46,29,47],[30,42,24,1,25],[30,23,15,28,16]],
  /* v32 */[[30,17,115,0,0],[28,10,46,23,47],[30,10,24,35,25],[30,19,15,35,16]],
  /* v33 */[[30,17,115,1,116],[28,14,46,21,47],[30,29,24,19,25],[30,11,15,46,16]],
  /* v34 */[[30,13,115,6,116],[28,14,46,23,47],[30,44,24,7,25],[30,59,16,1,17]],
  /* v35 */[[30,12,121,7,122],[28,12,47,26,48],[30,39,24,14,25],[30,22,15,41,16]],
  /* v36 */[[30,6,121,14,122],[28,6,47,34,48],[30,46,24,10,25],[30,2,15,64,16]],
  /* v37 */[[30,17,122,4,123],[28,29,46,14,47],[30,49,24,10,25],[30,24,15,46,16]],
  /* v38 */[[30,4,122,18,123],[28,13,46,32,47],[30,48,24,14,25],[30,42,15,32,16]],
  /* v39 */[[30,20,117,4,118],[28,40,47,7,48],[30,43,24,22,25],[30,10,15,67,16]],
  /* v40 */[[30,19,118,6,119],[28,18,47,31,48],[30,34,24,34,25],[30,20,15,61,16]],
];

// Posiciones de los patrones de alineación por versión (índice = versión−1). v1 no tiene.
// prettier-ignore
const ALIGN_POS: number[][] = [
  [], [6,18], [6,22], [6,26], [6,30], [6,34], [6,22,38], [6,24,42], [6,26,46], [6,28,50],
  [6,30,54], [6,32,58], [6,34,62], [6,26,46,66], [6,26,48,70], [6,26,50,74], [6,30,54,78],
  [6,30,56,82], [6,30,58,86], [6,34,62,90], [6,28,50,72,94], [6,26,50,74,98], [6,30,54,78,102],
  [6,28,54,80,106], [6,32,58,84,110], [6,30,58,86,114], [6,34,62,90,118], [6,26,50,74,98,122],
  [6,30,54,78,102,126], [6,26,52,78,104,130], [6,30,56,82,108,134], [6,34,60,86,112,138],
  [6,30,58,86,114,142], [6,34,62,90,118,146], [6,30,54,78,102,126,150], [6,24,50,76,102,128,154],
  [6,28,54,80,106,132,158], [6,32,58,84,110,136,162], [6,26,54,82,110,138,166],
  [6,30,58,86,114,142,170],
];

// Bits de información de versión (BCH) para v7+. Índice = versión−7.
// prettier-ignore
const VERSION_INFO = [
  0x07c94,0x085bc,0x09a99,0x0a4d3,0x0bbf6,0x0c762,0x0d847,0x0e60d,0x0f928,0x10b78,0x1145d,0x12a17,
  0x13532,0x149a6,0x15683,0x168c9,0x177ec,0x18ec4,0x191e1,0x1afab,0x1b08e,0x1cc1a,0x1d33f,0x1ed75,
  0x1f250,0x209d5,0x216f0,0x228ba,0x2379f,0x24b0b,0x2542e,0x26a64,0x27541,0x28c69,
];

// Bits de formato (EC level + máscara), pre-calculados con BCH + máscara XOR 0x5412.
// Índice = (ecBits << 3) | mask. ecBits: L=01, M=00, Q=11, H=10 (codificación del estándar).
// prettier-ignore
const FORMAT_INFO = [
  0x5412,0x5125,0x5e7c,0x5b4b,0x45f9,0x40ce,0x4f97,0x4aa0,
  0x77c4,0x72f3,0x7daa,0x789d,0x662f,0x6318,0x6c41,0x6976,
  0x1689,0x13be,0x1ce7,0x19d0,0x0762,0x0255,0x0d0c,0x083b,
  0x355f,0x3068,0x3f31,0x3a06,0x24b4,0x2183,0x2eda,0x2bed,
];
// Mapeo EC level → 2 bits índice usado en FORMAT_INFO.
const EC_FORMAT_BITS: Record<EcLevel, number> = { L: 1, M: 0, Q: 3, H: 2 };

// ───────────────────────── Escritor de bits ─────────────────────────
class BitBuffer {
  bits: number[] = [];
  put(value: number, length: number): void {
    for (let i = length - 1; i >= 0; i--) {
      this.bits.push((value >>> i) & 1);
    }
  }
  get length(): number {
    return this.bits.length;
  }
}

// Nº de bits del campo "character count" según versión y modo byte.
function charCountBits(version: number): number {
  return version <= 9 ? 8 : 16;
}

// Codifica `value` (UTF-8) en codewords de datos para una `version` y nivel `ec`.
// Devuelve null si no cabe.
function encodeData(bytes: Uint8Array, version: number, ec: EcLevel): Uint8Array | null {
  const totalCw = TOTAL_CODEWORDS[version - 1];
  const blocks = EC_BLOCKS[version - 1][EC_ORDER.indexOf(ec)];
  const ecPerBlock = blocks[0];
  const numBlocks = blocks[1] + blocks[3];
  const totalEcCw = ecPerBlock * numBlocks;
  const dataCwCapacity = totalCw - totalEcCw;
  const dataBitCapacity = dataCwCapacity * 8;

  const ccBits = charCountBits(version);
  const buf = new BitBuffer();
  buf.put(0b0100, 4); // indicador de modo BYTE
  buf.put(bytes.length, ccBits); // contador de caracteres
  for (const b of bytes) buf.put(b, 8);

  if (buf.length > dataBitCapacity) return null;

  // Terminador (hasta 4 bits) + padding a byte completo.
  const remaining = dataBitCapacity - buf.length;
  buf.put(0, Math.min(4, remaining));
  while (buf.length % 8 !== 0) buf.bits.push(0);

  // Bytes de relleno alternos 0xEC / 0x11 hasta llenar la capacidad de datos.
  const padBytes = [0xec, 0x11];
  let pi = 0;
  while (buf.length < dataBitCapacity) {
    buf.put(padBytes[pi], 8);
    pi ^= 1;
  }

  // Empaqueta a bytes.
  const dataCw = new Uint8Array(dataCwCapacity);
  for (let i = 0; i < dataCwCapacity; i++) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | buf.bits[i * 8 + j];
    dataCw[i] = byte;
  }

  // Reparte en bloques (grupo1 + grupo2), calcula EC por bloque e intercala.
  const dataBlocks: Uint8Array[] = [];
  const ecBlocks: Uint8Array[] = [];
  let offset = 0;
  const layout: number[][] = [];
  for (let g = 0; g < blocks[1]; g++) layout.push([blocks[2]]);
  for (let g = 0; g < blocks[3]; g++) layout.push([blocks[4]]);
  for (const [dlen] of layout) {
    const dblk = dataCw.slice(offset, offset + dlen);
    offset += dlen;
    dataBlocks.push(dblk);
    ecBlocks.push(rsEncode(dblk, ecPerBlock));
  }

  // Intercalado de codewords de datos (column-major) y luego de EC.
  const result = new Uint8Array(totalCw);
  let ri = 0;
  const maxData = Math.max(...dataBlocks.map((b) => b.length));
  for (let i = 0; i < maxData; i++) {
    for (const blk of dataBlocks) if (i < blk.length) result[ri++] = blk[i];
  }
  for (let i = 0; i < ecPerBlock; i++) {
    for (const blk of ecBlocks) result[ri++] = blk[i];
  }
  return result;
}

// ───────────────────────── Construcción de la matriz ─────────────────────────
// Matriz de módulos: 1 = oscuro, 0 = claro, null = sin asignar (zona de datos libre).
type Cell = 0 | 1 | null;

function buildMatrix(codewords: Uint8Array, version: number, ec: EcLevel): boolean[][] {
  const size = version * 4 + 17;
  const m: Cell[][] = Array.from({ length: size }, () => new Array<Cell>(size).fill(null));
  const reserved: boolean[][] = Array.from({ length: size }, () => new Array(size).fill(false));

  const set = (r: number, c: number, v: 0 | 1, isReserved = true): void => {
    m[r][c] = v;
    if (isReserved) reserved[r][c] = true;
  };

  // Patrón de detección de posición (finder) 7×7 + separador.
  const placeFinder = (r: number, c: number): void => {
    for (let dr = -1; dr <= 7; dr++) {
      for (let dc = -1; dc <= 7; dc++) {
        const rr = r + dr;
        const cc = c + dc;
        if (rr < 0 || rr >= size || cc < 0 || cc >= size) continue;
        const inRing =
          (dr >= 0 && dr <= 6 && (dc === 0 || dc === 6)) ||
          (dc >= 0 && dc <= 6 && (dr === 0 || dr === 6));
        const inCore = dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4;
        set(rr, cc, inRing || inCore ? 1 : 0);
      }
    }
  };
  placeFinder(0, 0);
  placeFinder(0, size - 7);
  placeFinder(size - 7, 0);

  // Patrones de tiempo (timing) en fila/columna 6.
  for (let i = 8; i < size - 8; i++) {
    const v: 0 | 1 = i % 2 === 0 ? 1 : 0;
    set(6, i, v);
    set(i, 6, v);
  }

  // Patrones de alineación (no se solapan con finders).
  const aps = ALIGN_POS[version - 1];
  for (const r of aps) {
    for (const c of aps) {
      if (reserved[r][c]) continue; // evita finders
      for (let dr = -2; dr <= 2; dr++) {
        for (let dc = -2; dc <= 2; dc++) {
          const ring = Math.max(Math.abs(dr), Math.abs(dc));
          set(r + dr, c + dc, ring === 1 ? 0 : 1);
        }
      }
    }
  }

  // Módulo oscuro fijo + reserva de zonas de formato.
  set(size - 8, 8, 1);
  for (let i = 0; i < 9; i++) {
    if (!reserved[8][i]) reserved[8][i] = true; // fila formato (arriba-izq)
    if (!reserved[i][8]) reserved[i][8] = true; // col formato
  }
  for (let i = 0; i < 8; i++) {
    reserved[8][size - 1 - i] = true; // formato derecho
    reserved[size - 1 - i][8] = true; // formato abajo
  }
  reserved[8][8] = true;
  reserved[8][7] = true;
  reserved[7][8] = true;

  // Reserva de información de versión (v7+): dos bloques 3×6.
  if (version >= 7) {
    for (let i = 0; i < 6; i++) {
      for (let j = 0; j < 3; j++) {
        reserved[i][size - 11 + j] = true;
        reserved[size - 11 + j][i] = true;
      }
    }
  }

  // Colocación de los bits de datos en zig-zag desde abajo-derecha.
  let bitIdx = 0;
  const totalBits = codewords.length * 8;
  const getBit = (idx: number): 0 | 1 =>
    idx < totalBits ? (((codewords[idx >> 3] >> (7 - (idx & 7))) & 1) as 0 | 1) : 0;

  let upward = true;
  for (let col = size - 1; col > 0; col -= 2) {
    if (col === 6) col--; // salta la columna de timing
    for (let i = 0; i < size; i++) {
      const row = upward ? size - 1 - i : i;
      for (let k = 0; k < 2; k++) {
        const c = col - k;
        if (reserved[row][c] || m[row][c] !== null) continue;
        m[row][c] = getBit(bitIdx);
        bitIdx++;
      }
    }
    upward = !upward;
  }

  // ───── Selección de máscara: prueba las 8 y elige la de menor penalización. ─────
  const maskFns: ((r: number, c: number) => boolean)[] = [
    (r, c) => (r + c) % 2 === 0,
    (r) => r % 2 === 0,
    (_r, c) => c % 3 === 0,
    (r, c) => (r + c) % 3 === 0,
    (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
    (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
    (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
    (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
  ];

  let bestMask = 0;
  let bestPenalty = Infinity;
  let bestMatrix: boolean[][] = [];

  for (let mask = 0; mask < 8; mask++) {
    const grid: boolean[][] = Array.from({ length: size }, () => new Array(size).fill(false));
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        let v = m[r][c] === 1;
        if (!reserved[r][c] && maskFns[mask](r, c)) v = !v;
        grid[r][c] = v;
      }
    }
    applyFormatAndVersion(grid, reserved, version, ec, mask);
    const penalty = scorePenalty(grid);
    if (penalty < bestPenalty) {
      bestPenalty = penalty;
      bestMask = mask;
      bestMatrix = grid;
    }
  }

  void bestMask;
  return bestMatrix;
}

// Aplica los bits de formato (EC + máscara) y, en v7+, la información de versión.
function applyFormatAndVersion(
  grid: boolean[][],
  _reserved: boolean[][],
  version: number,
  ec: EcLevel,
  mask: number,
): void {
  const size = grid.length;
  const fmt = FORMAT_INFO[(EC_FORMAT_BITS[ec] << 3) | mask];

  // Copia 1 (alrededor del finder superior-izquierdo).
  for (let i = 0; i < 15; i++) {
    const bit = ((fmt >> i) & 1) === 1;
    // Vertical (columna 8) y horizontal (fila 8), siguiendo el orden del estándar.
    if (i < 6) grid[i][8] = bit;
    else if (i === 6) grid[7][8] = bit;
    else if (i === 7) grid[8][8] = bit;
    else if (i === 8) grid[8][7] = bit;
    else grid[8][14 - i] = bit;

    if (i < 8) grid[8][size - 1 - i] = bit;
    else grid[size - 15 + i][8] = bit;
  }
  grid[size - 8][8] = true; // módulo oscuro siempre activo

  // Información de versión (v7+).
  if (version >= 7) {
    const vinfo = VERSION_INFO[version - 7];
    for (let i = 0; i < 18; i++) {
      const bit = ((vinfo >> i) & 1) === 1;
      const r = Math.floor(i / 3);
      const c = i % 3;
      grid[r][size - 11 + c] = bit;
      grid[size - 11 + c][r] = bit;
    }
  }
}

// Penalización de máscara (4 reglas del estándar) — menor es mejor.
function scorePenalty(grid: boolean[][]): number {
  const n = grid.length;
  let penalty = 0;

  // Regla 1: runs de 5+ módulos del mismo color en filas y columnas.
  const lineRun = (get: (i: number) => boolean): number => {
    let p = 0;
    let runColor = get(0);
    let runLen = 1;
    for (let i = 1; i < n; i++) {
      const v = get(i);
      if (v === runColor) {
        runLen++;
      } else {
        if (runLen >= 5) p += 3 + (runLen - 5);
        runColor = v;
        runLen = 1;
      }
    }
    if (runLen >= 5) p += 3 + (runLen - 5);
    return p;
  };
  for (let r = 0; r < n; r++) penalty += lineRun((c) => grid[r][c]);
  for (let c = 0; c < n; c++) penalty += lineRun((r) => grid[r][c]);

  // Regla 2: bloques 2×2 del mismo color.
  for (let r = 0; r < n - 1; r++) {
    for (let c = 0; c < n - 1; c++) {
      const v = grid[r][c];
      if (v === grid[r][c + 1] && v === grid[r + 1][c] && v === grid[r + 1][c + 1]) penalty += 3;
    }
  }

  // Regla 3: patrón 1:1:3:1:1 con 4 claros a un lado (finder-like) en filas y columnas.
  const pat1 = [true, false, true, true, true, false, true, false, false, false, false];
  const pat2 = [false, false, false, false, true, false, true, true, true, false, true];
  const matchAt = (get: (i: number) => boolean, start: number): boolean => {
    let a = true;
    let b = true;
    for (let k = 0; k < 11; k++) {
      const v = get(start + k);
      if (v !== pat1[k]) a = false;
      if (v !== pat2[k]) b = false;
    }
    return a || b;
  };
  for (let r = 0; r < n; r++) {
    for (let c = 0; c <= n - 11; c++) {
      if (matchAt((i) => grid[r][i], c)) penalty += 40;
    }
  }
  for (let c = 0; c < n; c++) {
    for (let r = 0; r <= n - 11; r++) {
      if (matchAt((i) => grid[i][c], r)) penalty += 40;
    }
  }

  // Regla 4: desviación de la proporción 50% de módulos oscuros.
  let dark = 0;
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (grid[r][c]) dark++;
  const ratio = (dark * 100) / (n * n);
  const k = Math.floor(Math.abs(ratio - 50) / 5);
  penalty += k * 10;

  return penalty;
}

// ───────────────────────── Orquestación ─────────────────────────
// Codifica `value` y devuelve la matriz booleana final (con la mejor máscara) o null si no cabe.
function generateQr(value: string, ec: EcLevel): boolean[][] | null {
  const bytes = new TextEncoder().encode(value);
  // Busca la versión más pequeña (1–40) que admita los datos con este nivel EC.
  for (let version = 1; version <= 40; version++) {
    const codewords = encodeData(bytes, version, ec);
    if (codewords) return buildMatrix(codewords, version, ec);
  }
  return null; // no cabe ni en v40
}

// ───────────────────────── Componente ─────────────────────────
export class OkQr extends LitElement {
  static styles = css`
    :host {
      /* Tokens overridables (cadena --ok-* → --ion-* → hex). */
      --module-color: var(--ok-text, var(--ion-text-color, #000000));
      --bg-color: var(--ok-surface, transparent);

      /* Inline: ocupa solo lo que necesita su tamaño. */
      display: inline-block;
      line-height: 0;
    }
    svg {
      display: block;
      width: var(--ok-qr-size, 160px);
      height: var(--ok-qr-size, 160px);
    }
    rect.qr-bg {
      fill: var(--bg-color);
    }
    path.qr-fg {
      fill: var(--module-color);
      shape-rendering: crispEdges;
    }
  `;

  /** Contenido a codificar (texto/URL). Si vacío, no pinta nada. */
  @property({ type: String }) value = '';
  /** Nivel de corrección de errores. */
  @property({ type: String }) ec: EcLevel = 'M';
  /** Lado del SVG en px. */
  @property({ type: Number }) size = 160;
  /** Color de los módulos (override directo del token). */
  @property({ type: String }) color = '';
  /** Color de fondo (override directo del token). */
  @property({ type: String }) background = '';
  /** Quiet zone en módulos alrededor del símbolo. */
  @property({ type: Number }) margin = 4;

  render(): unknown {
    if (!this.value) return html``;

    const level: EcLevel = EC_ORDER.includes(this.ec) ? this.ec : 'M';
    const matrix = generateQr(this.value, level);
    if (!matrix) return html``; // excede capacidad de v40: no rompe

    const count = matrix.length;
    const quiet = Math.max(0, Math.floor(this.margin));
    const dim = count + quiet * 2; // dimensión total en módulos (incl. quiet zone)

    // Un único <path> con todos los módulos oscuros (más eficiente que N <rect>).
    let d = '';
    for (let r = 0; r < count; r++) {
      for (let c = 0; c < count; c++) {
        if (matrix[r][c]) {
          d += `M${c + quiet} ${r + quiet}h1v1h-1z`;
        }
      }
    }

    // Overrides directos de color vía propiedades CSS inline (siguen siendo CSP-safe: style attr
    // estático, no inline scripts).
    const fg = this.color || undefined;
    const bg = this.background || undefined;

    const fgStyle = fg ? `fill:${fg}` : undefined;
    const bgStyle = bg ? `fill:${bg}` : undefined;

    const body: SVGTemplateResult = svg`
      <rect class="qr-bg" x="0" y="0" width="${dim}" height="${dim}" style="${bgStyle ?? ''}"></rect>
      <path class="qr-fg" d="${d}" style="${fgStyle ?? ''}"></path>
    `;

    return html`
      <svg
        style="width:${this.size}px;height:${this.size}px"
        viewBox="0 0 ${dim} ${dim}"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label=${`Código QR: ${this.value}`}
        shape-rendering="crispEdges"
      >
        ${body}
      </svg>
    `;
  }
}

define('ok-qr', OkQr);

declare global {
  interface HTMLElementTagNameMap {
    'ok-qr': OkQr;
  }
}
