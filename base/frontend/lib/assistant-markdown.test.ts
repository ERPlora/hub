// BASE-G113: the answer of the assistant read with its format (bold, lists, tables, links), never as HTML. Cases of
// the old hub's `assistant-markdown.test.ts`.
import { describe, expect, it } from 'vitest';

import { type Block, type Inline, linkPaths, parseMarkdown } from './assistant-markdown';

const text = (value: string): Inline => ({ kind: 'text', text: value });
const paragraph = (...inlines: Inline[]): Block => ({ kind: 'paragraph', inlines });

describe('parseMarkdown', () => {
  it('a text without markdown comes out whole, in one paragraph', () => {
    expect(parseMarkdown('Tienes 3 citas hoy.\nLa primera a las 10.')).toEqual([
      paragraph(text('Tienes 3 citas hoy.\nLa primera a las 10.')),
    ]);
  });

  it('the person no longer sees the asterisks of bold, nor of italics', () => {
    expect(parseMarkdown('Total: **15,00 €** y *sin IVA*')).toEqual([
      paragraph(
        text('Total: '),
        { kind: 'strong', children: [text('15,00 €')] },
        text(' y '),
        { kind: 'em', children: [text('sin IVA')] },
      ),
    ]);
  });

  it('inline code is marked, without its backticks, and nothing inside it is read', () => {
    expect(parseMarkdown('Usa `**no**` aquí')).toEqual([
      paragraph(text('Usa '), { kind: 'code', text: '**no**' }, text(' aquí')),
    ]);
  });

  it('a lone asterisk does not swallow half the answer, nor do two of a multiplication', () => {
    expect(parseMarkdown('Precio * 2')).toEqual([paragraph(text('Precio * 2'))]);
    expect(parseMarkdown('2 * 3 * 4 = 24')).toEqual([paragraph(text('2 * 3 * 4 = 24'))]);
  });

  it('a heading carries its level and not its hashes', () => {
    expect(parseMarkdown('## Ventas de hoy')).toEqual([{ kind: 'heading', level: 2, inlines: [text('Ventas de hoy')] }]);
  });

  it('a bulleted list and a numbered one', () => {
    expect(parseMarkdown('- Uno\n- **Dos**')).toEqual([
      { kind: 'list', ordered: false, items: [[text('Uno')], [{ kind: 'strong', children: [text('Dos')] }]] },
    ]);
    expect(parseMarkdown('1. Primero\n2. Segundo')).toEqual([
      { kind: 'list', ordered: true, items: [[text('Primero')], [text('Segundo')]] },
    ]);
  });

  it('a table is read with its head and its rows', () => {
    expect(parseMarkdown('| Producto | Uds |\n|---|---:|\n| Caña | 12 |\n| Tapa | 3 |')).toEqual([
      {
        kind: 'table',
        head: [[text('Producto')], [text('Uds')]],
        rows: [
          [[text('Caña')], [text('12')]],
          [[text('Tapa')], [text('3')]],
        ],
      },
    ]);
  });

  it('a loose line with bars is no table', () => {
    expect(parseMarkdown('Mesa 1 | Mesa 2')).toEqual([paragraph(text('Mesa 1 | Mesa 2'))]);
  });

  it('a link shows its label, never the brackets nor the path', () => {
    expect(parseMarkdown('Ve a [tus ajustes](/settings#business).')).toEqual([
      paragraph(text('Ve a '), { kind: 'link', path: '/settings#business', label: [text('tus ajustes')] }, text('.')),
    ]);
  });

  it('a web address is never a link: its label stays as text', () => {
    expect(parseMarkdown('Mira [esto](https://evil.example/settings)')).toEqual([paragraph(text('Mira esto'))]);
    expect(parseMarkdown('Mira [esto](//evil.example)')).toEqual([paragraph(text('Mira esto'))]);
  });

  it('a bare path of a screen becomes a link the panel names', () => {
    expect(parseMarkdown('Está en /customer/customers ahora')).toEqual([
      paragraph(text('Está en '), { kind: 'link', path: '/customer/customers', label: null }, text(' ahora')),
    ]);
  });

  it('the path of a web address is not taken for a screen of the hub', () => {
    expect(parseMarkdown('Ver https://erplora.com/settings')).toEqual([paragraph(text('Ver https://erplora.com/settings'))]);
  });

  it('a path inside code stays readable whole', () => {
    expect(parseMarkdown('Abre `/settings`')).toEqual([paragraph(text('Abre '), { kind: 'code', text: '/settings' })]);
  });

  it('a list item keeps its link, and emphasis inside a label is read once', () => {
    expect(parseMarkdown('- [**Clientes**](/customer/customers)')).toEqual([
      {
        kind: 'list',
        ordered: false,
        items: [[{ kind: 'link', path: '/customer/customers', label: [{ kind: 'strong', children: [text('Clientes')] }] }]],
      },
    ]);
  });

  it('HTML is text: nothing of the answer is ever interpreted as a tag', () => {
    expect(parseMarkdown('<img src=x onerror=alert(1)>')).toEqual([paragraph(text('<img src=x onerror=alert(1)>'))]);
  });
});

describe('linkPaths', () => {
  it('the screens an answer names, once each and in order', () => {
    const blocks = parseMarkdown('Ve a [Ajustes](/settings) o a /apps; luego [Ajustes](/settings).');
    expect(linkPaths(blocks)).toEqual(['/settings', '/apps']);
  });
});
