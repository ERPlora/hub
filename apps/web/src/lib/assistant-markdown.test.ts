// El drawer pintaba markdown CRUDO (hub#1043): el usuario leía `**Multi-tenant**`, `` `1250` `` y,
// lo peor, tablas enteras como una sopa de barras verticales. Un asistente de ERP responde
// constantemente con datos tabulares —tipos de IVA, módulos instalados, ventas por día— así que la
// tabla es el formato natural de la respuesta y era justo el que peor se degradaba.
//
// Se parsea a ESTRUCTURA y lo pinta Vue. No se genera HTML ni se usa `v-html`: hoy no hay uno solo
// en todo el web del hub, y el primero no va a estrenarse sobre texto que escribe un LLM. Sin HTML
// no hay que sanear nada, no hace falta un DOMPurify, y la CSP estricta (`script-src 'self'`,
// ADR-0050/0308) no entra en juego.

import { describe, expect, it } from 'vitest';

import { parseMarkdown } from './assistant-markdown';

/**
 * El texto plano de un bloque, para afirmar sin recorrer spans a mano. A bare screen path is a
 * link with no label of its own (hub#2204) — the drawer names it — so it reads as its target here.
 */
function textOf(spans: { text: string; href?: string }[]): string {
  return spans.map((s) => s.text || s.href || '').join('');
}

describe('parseMarkdown — énfasis y código', () => {
  it('el usuario deja de ver los asteriscos', () => {
    const [block] = parseMarkdown('ERPlora es un **ERP/POS modular** de verdad.');

    expect(block.type).toBe('paragraph');
    if (block.type !== 'paragraph') return;
    expect(textOf(block.spans)).toBe('ERPlora es un ERP/POS modular de verdad.');
    expect(block.spans.some((s) => s.kind === 'bold' && s.text === 'ERP/POS modular')).toBe(true);
  });

  it('el código en línea se marca, no se enseña con las comillas', () => {
    const [block] = parseMarkdown('12,50 € se envía como `1250`.');

    if (block.type !== 'paragraph') throw new Error('párrafo');
    expect(textOf(block.spans)).toBe('12,50 € se envía como 1250.');
    expect(block.spans.some((s) => s.kind === 'code' && s.text === '1250')).toBe(true);
  });

  it('la cursiva también', () => {
    const [block] = parseMarkdown('cada *hub* es suyo');
    if (block.type !== 'paragraph') throw new Error('párrafo');
    expect(block.spans.some((s) => s.kind === 'italic' && s.text === 'hub')).toBe(true);
  });
});

describe('parseMarkdown — la tabla, que era lo ilegible', () => {
  it('una tabla se parsea con su cabecera y sus filas', () => {
    const md = [
      '| Módulo | Para qué | Ruta |',
      '|---|---|---|',
      '| `staff` | Personal | /m/staff/staff |',
      '| `taxes` | Impuestos | /m/taxes/categories |',
    ].join('\n');

    const [block] = parseMarkdown(md);

    expect(block.type).toBe('table');
    if (block.type !== 'table') return;
    expect(block.head.map(textOf)).toEqual(['Módulo', 'Para qué', 'Ruta']);
    expect(block.rows).toHaveLength(2);
    expect(block.rows[0].map(textOf)).toEqual(['staff', 'Personal', '/m/staff/staff']);
    // El contenido de las celdas también se formatea: `staff` iba en comillas.
    expect(block.rows[0][0][0].kind).toBe('code');
    // …and a screen path in a cell is a link the drawer names (hub#2204), not a path to read.
    expect(block.rows[0][2][0]).toEqual({ kind: 'link', text: '', href: '/m/staff/staff' });
  });

  it('una línea suelta con barras NO es una tabla', () => {
    // Sin fila separadora no hay tabla; convertirla dejaría frases partidas en columnas.
    const [block] = parseMarkdown('El horario es de 9|10 según el día.');
    expect(block.type).toBe('paragraph');
  });
});

describe('parseMarkdown — listas y encabezados', () => {
  it('una lista con viñetas se parsea como lista', () => {
    const [block] = parseMarkdown('- Uno\n- **Dos**\n- Tres');

    expect(block.type).toBe('list');
    if (block.type !== 'list') return;
    expect(block.items).toHaveLength(3);
    expect(textOf(block.items[1])).toBe('Dos');
  });

  it('un encabezado lleva su nivel y no sus almohadillas', () => {
    const [block] = parseMarkdown('### Cómo actualizar el precio');

    expect(block.type).toBe('heading');
    if (block.type !== 'heading') return;
    expect(block.level).toBe(3);
    expect(textOf(block.spans)).toBe('Cómo actualizar el precio');
  });
});

describe('parseMarkdown — no rompe lo que ya funcionaba', () => {
  // hub#1038/#1048: las rutas se extraen del texto FUENTE para ofrecer los CTAs «Ir a…» y para
  // el audit de anclaje. El parseo no puede comerse una ruta ni partirla.
  it('una ruta dentro de código sigue siendo legible entera', () => {
    const [block] = parseMarkdown('Lo tienes en `/m/services/services`.');
    if (block.type !== 'paragraph') throw new Error('párrafo');
    expect(textOf(block.spans)).toContain('/m/services/services');
  });

  it('un texto sin markdown sale intacto, en un solo párrafo', () => {
    const md = 'Tienes 40 servicios en el catálogo.';
    const blocks = parseMarkdown(md);
    expect(blocks).toHaveLength(1);
    if (blocks[0].type !== 'paragraph') throw new Error('párrafo');
    expect(textOf(blocks[0].spans)).toBe(md);
  });

  it('un asterisco suelto no se traga media respuesta', () => {
    const [block] = parseMarkdown('El total * 2 son 40 €');
    if (block.type !== 'paragraph') throw new Error('párrafo');
    expect(textOf(block.spans)).toBe('El total * 2 son 40 €');
  });

  // El caso que DISCRIMINA de verdad: con DOS asteriscos una cursiva permisiva sí encontraría
  // pareja y se comería « 2 » como énfasis. Con uno solo el test pasaba por casualidad — lo
  // descubrí saboteando la regla y viendo que nadie se quejaba.
  it('dos asteriscos de multiplicar tampoco abren cursiva', () => {
    const [block] = parseMarkdown('El total * 2 * 3 son 240 €');
    if (block.type !== 'paragraph') throw new Error('párrafo');
    expect(textOf(block.spans)).toBe('El total * 2 * 3 son 240 €');
    expect(block.spans.every((s) => s.kind === 'text')).toBe(true);
  });

  // Dentro de `` `…` `` no se interpreta nada, porque el match del código CONSUME su contenido.
  // (No es cuestión del orden de la lista de marcas: eso lo comprobé reordenándola y no cambia
  // nada — gana la marca que aparece antes en el texto.)
  it('dentro de código no se interpreta el énfasis', () => {
    const [block] = parseMarkdown('La fórmula es `precio * cantidad * iva` en céntimos.');
    if (block.type !== 'paragraph') throw new Error('párrafo');
    const code = block.spans.find((s) => s.kind === 'code');
    expect(code?.text).toBe('precio * cantidad * iva');
    expect(block.spans.some((s) => s.kind === 'italic')).toBe(false);
  });
});

// hub#2204 — the owner read «→ Ve a: [Ajustes de facturación](/m/invoice/settings)» with the
// brackets, the parentheses and the path on screen. A link is a span of its own: the label is
// what is read, the target travels beside it and the drawer decides whether it is clickable.
describe('parseMarkdown — links (hub#2204)', () => {
  it('a Markdown link shows its label, never the brackets or the path', () => {
    const [block] = parseMarkdown('→ Ve a: [Ajustes de facturación](/m/invoice/settings)');
    if (block.type !== 'paragraph') throw new Error('párrafo');

    expect(textOf(block.spans)).toBe('→ Ve a: Ajustes de facturación');
    expect(block.spans).toContainEqual({ kind: 'link', text: 'Ajustes de facturación', href: '/m/invoice/settings' });
  });

  it('a bare screen path becomes a link with no label of its own — the drawer names it', () => {
    const [block] = parseMarkdown('Ve a /m/invoice/settings y activa la serie.');
    if (block.type !== 'paragraph') throw new Error('párrafo');

    expect(block.spans).toContainEqual({ kind: 'link', text: '', href: '/m/invoice/settings' });
    expect(
      block.spans
        .filter((s) => s.kind === 'text')
        .map((s) => s.text)
        .join(''),
    ).not.toContain('/m/');
  });

  it('the path of a web address is not mistaken for a screen of the hub', () => {
    const [block] = parseMarkdown('Consulta https://erplora.com/apps para más.');
    if (block.type !== 'paragraph') throw new Error('párrafo');

    expect(block.spans.some((s) => s.kind === 'link')).toBe(false);
    expect(textOf(block.spans)).toBe('Consulta https://erplora.com/apps para más.');
  });

  it('inside a link label the emphasis is not parsed twice and the link keeps its target', () => {
    const [block] = parseMarkdown('**Paso 1:** abre [Caja](/m/cash_register) ahora');
    if (block.type !== 'paragraph') throw new Error('párrafo');

    expect(block.spans[0]).toEqual({ kind: 'bold', text: 'Paso 1:' });
    expect(block.spans).toContainEqual({ kind: 'link', text: 'Caja', href: '/m/cash_register' });
  });

  it('a list item keeps its link too', () => {
    const [block] = parseMarkdown('- [Empleados](/employees)');
    if (block.type !== 'list') throw new Error('lista');

    expect(block.items[0]).toEqual([{ kind: 'link', text: 'Empleados', href: '/employees' }]);
  });

  it('emphasis marks inside a link label are not read', () => {
    const [block] = parseMarkdown('Abre [**Caja**](/m/cash_register).');
    if (block.type !== 'paragraph') throw new Error('párrafo');

    expect(block.spans).toContainEqual({ kind: 'link', text: 'Caja', href: '/m/cash_register' });
  });

  it('a screen path followed by more path is not a screen of the hub', () => {
    const [block] = parseMarkdown('Ve a /m/invoice/settings/advanced o a /settings/extra.');
    if (block.type !== 'paragraph') throw new Error('párrafo');

    expect(block.spans.some((s) => s.kind === 'link')).toBe(false);
  });
});
