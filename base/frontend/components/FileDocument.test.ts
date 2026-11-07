// Files › the preview of a Word document (hub#578, BASE-F74): its text with its basic formatting (headings, bold,
// italics, lists, tables, links), drawn element by element from the tree `readDocument` keeps — never HTML painted
// (`v-html`/`innerHTML`, which Trusted Types refuses). A `<script>` or an `onerror` in a .docx never reaches the page.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import { documentNodes, type DocumentNode, readDocument } from '../lib/office';
import FileDocument from './FileDocument.vue';

const SAMPLE = new Uint8Array(readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '__tests__', 'files', 'sample.docx')));

async function document_(nodes: DocumentNode[], locale: 'en' | 'es' = 'en') {
  const m = await mountBase(FileDocument, { props: { nodes }, locale });
  await flush();
  return m.wrapper;
}

describe('FileDocument', () => {
  it('draws a real .docx with its headings, bold, italics, lists and tables', async () => {
    const wrapper = await document_(await readDocument(SAMPLE));
    const page = wrapper.find('[data-testid="file-preview-document"]');
    expect(page.find('h1').text()).toBe('Informe de noviembre');
    expect(page.find('h2').text()).toBe('Pendiente');
    expect(page.find('strong').text()).toBe('fuerza');
    expect(page.find('em').text()).toBe('cada día');
    expect(page.findAll('ul li').map((item) => item.text())).toEqual(['Pedir café', 'Revisar la cámara']);
    expect(page.findAll('ol li').map((item) => item.text())).toEqual(['Cerrar el mes', 'Enviar a la gestoría']);
    expect(page.findAll('td').map((cell) => cell.text())).toEqual(['Producto', 'Unidades', 'Café solo', '120']);
  });

  it('a <script> or an onerror of a .docx never reaches the page: its text that looks like markup stays text', async () => {
    const wrapper = await document_(await readDocument(SAMPLE));
    const page = wrapper.element;
    expect(page.querySelector('script')).toBeNull();
    expect(page.querySelector('img')).toBeNull();
    expect(page.querySelectorAll('[onerror], [onclick], [style]')).toHaveLength(0);
    expect(page.textContent).toContain('<script>alert(1)</script> y <img src=x onerror=alert(2)>');
    // Its `javascript:` link keeps its words and no address.
    expect([...page.querySelectorAll('a')].map((link) => link.getAttribute('href'))).toEqual(['https://erplora.com/']);
  });

  it('nor when the HTML it comes from carries them as elements', async () => {
    const wrapper = await document_(
      await documentNodes('<p>a<script>alert(1)</script><img src="x" onerror="alert(2)"><b onmouseover="alert(3)">b</b></p>'),
    );
    expect(wrapper.element.querySelector('script, img, [onerror], [onmouseover]')).toBeNull();
    expect(wrapper.find('[data-testid="file-preview-document"]').text()).toBe('ab');
  });

  it('a link opens apart from the hub, without telling the page it came from', async () => {
    const wrapper = await document_([{ tag: 'p', attrs: {}, children: [{ tag: 'a', attrs: { href: 'https://erplora.com/' }, children: ['web'] }] }]);
    const link = wrapper.find('a');
    expect(link.attributes()).toMatchObject({ href: 'https://erplora.com/', target: '_blank', rel: 'noopener noreferrer' });
  });

  it('an image of the document and the span of a cell are kept', async () => {
    const wrapper = await document_([
      { tag: 'p', attrs: {}, children: [{ tag: 'img', attrs: { src: 'data:image/png;base64,iVBORw0KGgo=', alt: 'logo' }, children: [] }] },
      { tag: 'table', attrs: {}, children: [{ tag: 'tr', attrs: {}, children: [{ tag: 'td', attrs: { colspan: '2' }, children: ['x'] }] }] },
    ]);
    expect(wrapper.find('img').attributes()).toMatchObject({ src: 'data:image/png;base64,iVBORw0KGgo=', alt: 'logo' });
    expect(wrapper.find('td').attributes('colspan')).toBe('2');
  });

  it('a document with no text says so', async () => {
    expect((await document_([], 'es')).find('[data-testid="file-preview-document-empty"]').text()).toBe('Este documento no tiene texto.');
    expect((await document_([{ tag: 'p', attrs: {}, children: [] }])).find('[data-testid="file-preview-document-empty"]').text()).toBe(
      'This document has no text.',
    );
  });
});
