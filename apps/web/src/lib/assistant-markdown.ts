// Markdown del asistente, parseado a ESTRUCTURA (hub#1043).
//
// El drawer pintaba el markdown crudo: el usuario leía `**Multi-tenant**`, `` `1250` `` y, lo
// peor, tablas enteras como una sopa de barras verticales. Un asistente de ERP responde
// constantemente con datos tabulares —tipos de IVA, módulos instalados, ventas por día—, así que
// la tabla es el formato NATURAL de la respuesta y era justo el que peor se degradaba. A ~390 px
// cada fila se partía en tres líneas con las barras huérfanas.
//
// **Por qué un parser propio y no `markdown-it` + DOMPurify**, que es lo que sugería la issue:
// generar HTML obligaría a pintarlo con `v-html`, y hoy no hay UN SOLO `v-html` en todo el web
// del hub. El primero no va a estrenarse sobre texto que escribe un LLM. Devolviendo estructura,
// la pinta Vue con sus propias plantillas: escapa el texto por definición, no hay que sanear
// nada, no entra una dependencia nueva y la CSP estricta (ADR-0050/0308) ni se roza.
//
// El subconjunto es el que el asistente usa de verdad —énfasis, código, listas, encabezados y
// tablas—, no CommonMark entero. Lo que no se reconoce se queda como texto, que es la degradación
// correcta: peor formateado nunca es peor que ilegible.

export type Inline = { kind: 'text' | 'bold' | 'italic' | 'code'; text: string };
export type Block =
  | { type: 'paragraph'; spans: Inline[] }
  | { type: 'heading'; level: number; spans: Inline[] }
  | { type: 'list'; ordered: boolean; items: Inline[][] }
  | { type: 'table'; head: Inline[][]; rows: Inline[][][] };

/**
 * Marcas EN LÍNEA. Gana la que aparece ANTES en el texto, no la primera de esta lista: el orden
 * aquí solo desempata, y comprobé saboteándolo que reordenarla no cambia ningún resultado.
 *
 * Lo que sí protege el contenido de `` `…` `` es que su match lo CONSUME: el resto se sigue
 * parseando después del cierre, así que un `precio * cantidad` dentro de comillas no abre
 * cursiva. La garantía es esa, no la posición en esta lista.
 */
const INLINE = [
  { kind: 'code' as const, re: /`([^`]+)`/ },
  { kind: 'bold' as const, re: /\*\*([^*]+)\*\*/ },
  // Un asterisco suelto («El total * 2») NO abre cursiva: se exige contenido sin espacios a los
  // lados, que es lo que separa el énfasis de la multiplicación.
  { kind: 'italic' as const, re: /\*(\S[^*]*\S|\S)\*/ },
];

/** Parte una línea en spans. Nunca lanza: una respuesta mal formateada se lee, una excepción no. */
export function parseInline(text: string): Inline[] {
  let earliest: { kind: Inline['kind']; index: number; length: number; inner: string } | null = null;
  for (const { kind, re } of INLINE) {
    const m = re.exec(text);
    if (m && (earliest === null || m.index < earliest.index)) {
      earliest = { kind, index: m.index, length: m[0].length, inner: m[1] };
    }
  }
  if (!earliest) return text ? [{ kind: 'text', text }] : [];

  const before = text.slice(0, earliest.index);
  const after = text.slice(earliest.index + earliest.length);
  return [
    ...(before ? [{ kind: 'text' as const, text: before }] : []),
    { kind: earliest.kind, text: earliest.inner },
    ...parseInline(after),
  ];
}

/** Las celdas de una fila `| a | b |`, sin los bordes. */
function cells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim());
}

/** ¿Es la fila separadora de una tabla (`|---|---|`)? Sin ella no hay tabla. */
function isSeparator(line: string): boolean {
  const t = line.trim();
  return /^\|?[\s:-]*\|[\s:|-]*$/.test(t) && t.includes('-');
}

export function parseMarkdown(text: string): Block[] {
  const lines = (text ?? '').split('\n');
  const blocks: Block[] = [];
  let paragraph: string[] = [];

  const flush = (): void => {
    if (paragraph.length === 0) return;
    blocks.push({ type: 'paragraph', spans: parseInline(paragraph.join(' ').trim()) });
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      flush();
      continue;
    }

    // Tabla: cabecera + separadora. Se exige la separadora para que una frase con una barra
    // suelta («de 9|10 según el día») no se convierta en columnas.
    if (trimmed.includes('|') && i + 1 < lines.length && isSeparator(lines[i + 1])) {
      flush();
      const head = cells(trimmed).map(parseInline);
      const rows: Inline[][][] = [];
      let j = i + 2;
      for (; j < lines.length && lines[j].includes('|') && lines[j].trim(); j++) {
        rows.push(cells(lines[j]).map(parseInline));
      }
      blocks.push({ type: 'table', head, rows });
      i = j - 1;
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) {
      flush();
      blocks.push({ type: 'heading', level: heading[1].length, spans: parseInline(heading[2]) });
      continue;
    }

    const bullet = /^[-*+]\s+(.*)$/.exec(trimmed);
    const numbered = /^\d+[.)]\s+(.*)$/.exec(trimmed);
    if (bullet || numbered) {
      flush();
      const ordered = !bullet;
      const items: Inline[][] = [];
      let j = i;
      for (; j < lines.length; j++) {
        const t = lines[j].trim();
        const b = /^[-*+]\s+(.*)$/.exec(t);
        const n = /^\d+[.)]\s+(.*)$/.exec(t);
        if (ordered ? !n : !b) break;
        items.push(parseInline((ordered ? n! : b!)[1]));
      }
      blocks.push({ type: 'list', ordered, items });
      i = j - 1;
      continue;
    }

    paragraph.push(trimmed);
  }
  flush();
  return blocks;
}
