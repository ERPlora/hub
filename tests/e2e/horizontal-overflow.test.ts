// flow: e2e-overflow — FIX of the e2e harness (FIX-HUB-E2E-HORIZONTAL-SCROLL-CHECK-BLIND-TO-ION-CONTENT)
// Every «no horizontal scroll» check of the e2e goes through `horizontalOverflow(page)` (helpers.ts), which reads the
// document and every `ion-content` on screen. A spec that measures the document by hand (`documentElement.scrollWidth`
// against the window) is blind to a screen cut inside `ion-content`: Ionic pins the `body`, so the document never grows
// (60 files of the e2e did, and a 1600 px block on a page at 390 passed). No ratchet: no file but helpers.ts measures it.
// Nor through a name given to the root (`const root = document.documentElement; root.scrollWidth`), nor one `ion-content`
// by hand (its `getScrollElement()`, `.inner-scroll` or `part="scroll"` and their `scrollWidth`): that copy left out the
// menu and the sheets (seen by the reviewer of hub#393). Nor its width destructured (`const { scrollWidth } = document.
// documentElement`), the root found by its selector or a locator (`page.locator('html')`), or a measure split over lines
// (seen by the reviewer of saas#153). Its vertical scroll (`scrollTop`, `scrollHeight`) stays free.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The file of the one measure. */
const HELPERS = 'helpers.ts';

/** The document's root found by its selector: `querySelector('html')`, `'body'` or `':root'`. */
const ROOT_QUERY = String.raw`querySelector(?:<[^>]*>)?\(\s*['"\x60](?:html|body|:root)['"\x60]\s*\)`;

/** The ways of reading how wide the document is: its root's, its scrolling element's or its body's `scrollWidth`, the root
 *  found by its selector too, also closed in a parenthesis or through `as` (`(document.scrollingElement ?? document.documentElement).scrollWidth`). */
const DOCUMENT_WIDTH = new RegExp(
  String.raw`\b(?:documentElement|scrollingElement|document\s*\.\s*body|${ROOT_QUERY})\s*!?(?:\s*as\s+[^);]+)?\s*\)?\s*!?\s*\??\.\s*scrollWidth\b`,
);

/** An `ion-content`'s scroll box read right there: `(await content.getScrollElement()).scrollWidth`, its `then()`, `….scrollWidth`
 *  of its `.inner-scroll` or its `part="scroll"`. */
const SCROLL_BOX_WIDTH =
  /(?:getScrollElement\(\)|inner-scroll|part~?=["']?scroll)[^;\n]*?(?:\)|=>\s*\w+)\s*!?\s*\??\.\s*scrollWidth\b/;

/** The root found by a locator of Playwright and its width read in the same statement: `page.locator('html').evaluate(
 *  (html) => html.scrollWidth …)`, `page.$eval('body', …)`. */
const ROOT_LOCATOR_WIDTH = /(?:\blocator|\$eval|\$)\(\s*['"`](?:html|body|:root)['"`][^;]*\bscrollWidth\b/;

/** The document's root by any of its names (`document.documentElement`, `.scrollingElement`, `.body`, `querySelector('html')`). */
const ROOT = String.raw`(?:(?:window|globalThis)\s*\.\s*)?document\s*\.\s*(?:documentElement|scrollingElement|body|${ROOT_QUERY})\s*!?`;

/** A name given to the root (`const root = document.documentElement`, `?? document.body`, `as HTMLElement`). */
const ROOT_NAME = new RegExp(
  String.raw`\b(?:const|let|var)\s+(\w+)(?:\s*:[^=]+)?\s*=\s*\(?\s*${ROOT}(?:\s*(?:\?\?|\|\|)\s*${ROOT})*\s*(?:as\s+[^;,)]+)?\)?\s*(?:[;,)]|$)`,
);

/** The names a destructuring of `document` gives to the root (`const { body, documentElement: html } = document`). */
const ROOT_DESTRUCTURED = /\b(?:const|let|var)\s*\{([^}]*)\}\s*=\s*document\s*(?:[;,)]|$)/;

/** A name given to an `ion-content`'s scroll box: from its `getScrollElement()`, its `.inner-scroll` or its `part="scroll"`. */
const SCROLL_BOX_NAME = /\b(?:const|let|var)\s+(\w+)(?:\s*:[^=]+)?\s*=[^;\n]*(?:getScrollElement\(|inner-scroll|part~?=["']?scroll)/;

/** A `scrollWidth` taken out by destructuring (`const { scrollWidth } = …`, also nested), and what it is taken from. */
const WIDTH_DESTRUCTURED = /\{[^{}]*\bscrollWidth\b[^{}]*\}[\s}]*=\s*(?:await\s+)?\(?\s*([^;\n]*)/;

/** What that destructuring measures by hand: the root (or `document`, destructured down to it) or a scroll box. */
const MEASURED_BOX = new RegExp(String.raw`^(?:${ROOT}|document\s*$)|getScrollElement\(|inner-scroll|part~?=["']?scroll`);

/**
 * The statements of `source`, each with the line it starts on: a line that goes on with a chain (`.x`, `?.x`) is joined to
 * the one before it, so that a measure split over lines (`document.documentElement` and `.scrollWidth` below) reads as one.
 */
function statements(source: string): Array<{ line: number; text: string }> {
  const found: Array<{ line: number; text: string }> = [];
  source.split('\n').forEach((text, index) => {
    const last = found.at(-1);
    if (last && /^\s*\??\.(?!\.)/.test(text)) last.text += text.trim();
    else found.push({ line: index + 1, text });
  });
  return found;
}

/** The names `source` gives to the document's root or to an `ion-content`'s scroll box. */
function boxNames(source: string): string[] {
  const names = new Set<string>();
  for (const { text } of statements(source)) {
    const named = text.match(ROOT_NAME) ?? text.match(SCROLL_BOX_NAME);
    if (named) names.add(named[1]);
    for (const entry of text.match(ROOT_DESTRUCTURED)?.[1].split(',') ?? []) {
      const [key, alias] = entry.split(':').map((part) => part.trim());
      if (/^(?:documentElement|scrollingElement|body)$/.test(key)) names.add(alias || key);
    }
  }
  return [...names];
}

/**
 * `file:line` of each statement of `source` (the file `name`) that measures by hand how wide the document or one
 * `ion-content` is: its `scrollWidth`, read directly, through a name given to it, taken by a destructuring or through a
 * locator of the root. A vertical read (`scrollTop`, `scrollHeight`) is no such measure.
 */
function documentMeasures(name: string, source: string): string[] {
  const names = boxNames(source);
  const named = names.length ? new RegExp(String.raw`\b(?:${names.join('|')})\s*!?\s*\??\.\s*scrollWidth\b`) : null;
  const namedBox = names.length ? new RegExp(String.raw`^(?:${names.join('|')})\b`) : null;
  const destructured = (text: string) => {
    const from = text.match(WIDTH_DESTRUCTURED)?.[1];
    return from !== undefined && (MEASURED_BOX.test(from) || !!namedBox?.test(from));
  };
  const measures = [DOCUMENT_WIDTH, SCROLL_BOX_WIDTH, ROOT_LOCATOR_WIDTH, ...(named ? [named] : [])];
  return statements(source).flatMap(({ line, text }) =>
    measures.some((measure) => measure.test(text)) || destructured(text) ? [`${name}:${line}`] : [],
  );
}

/** The files of the e2e (the specs and their helpers, not Vitest's own tests) that measure the document by hand. */
function handMeasures(): string[] {
  return readdirSync(E2E_DIR)
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts') && name !== HELPERS)
    .sort()
    .flatMap((name) => documentMeasures(name, readFileSync(join(E2E_DIR, name), 'utf8')));
}

describe('the e2e checks for a horizontal scroll go through horizontalOverflow() of helpers.ts', () => {
  it('no file of tests/e2e but helpers.ts measures the document by hand: the check is horizontalOverflow(page)', () => {
    expect(handMeasures()).toEqual([]);
  });

  it('helpers.ts has the one measure, and it reads the document and the scroll box of every ion-content', () => {
    const helpers = readFileSync(join(E2E_DIR, HELPERS), 'utf8');
    expect(helpers).toContain('export async function horizontalOverflow(page: Page): Promise<number>');
    expect(helpers).toContain('const boxes: Element[] = [document.documentElement];');
    expect(helpers).toContain("for (const content of document.querySelectorAll('ion-content'))");
    expect(helpers).toContain(`content.shadowRoot?.querySelector('[part~="scroll"]')`);
  });

  it('the count reads every way of measuring the document by hand, and the helper or an element’s own width as none', () => {
    const lines = [
      'page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)',
      'page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)',
      '      documentScrollWidth: document.documentElement.scrollWidth,',
      'return document.scrollingElement!.scrollWidth - innerWidth;',
      'return document.body.scrollWidth > innerWidth;',
    ];
    expect(lines.map((line) => documentMeasures('x.ts', line))).toEqual(lines.map(() => ['x.ts:1']));
    expect(documentMeasures('x.ts', 'expect.poll(() => horizontalOverflow(page)).toBeLessThanOrEqual(0);')).toEqual([]);
    expect(documentMeasures('x.ts', 'label.scrollWidth > label.clientWidth + 1')).toEqual([]);
    expect(documentMeasures('x.ts', 'const body = el.querySelector(".drawer-body"); body.scrollWidth > body.clientWidth')).toEqual([]);
  });

  it('the count reads the document measured through a name given to its root', () => {
    const root = ['page.evaluate(() => {', '  const root = document.documentElement;', '  return root.scrollWidth - window.innerWidth;', '});'];
    expect(documentMeasures('a.ts', root.join('\n'))).toEqual(['a.ts:3']);
    const either = ['const root = document.scrollingElement ?? document.documentElement;', 'return root!.scrollWidth > innerWidth;'];
    expect(documentMeasures('a.ts', either.join('\n'))).toEqual(['a.ts:2']);
    const destructured = ['const { body, documentElement: html } = document;', 'return [body.scrollWidth, html.scrollWidth];'];
    expect(documentMeasures('a.ts', destructured.join('\n'))).toEqual(['a.ts:2']);
  });

  it('the count reads one ion-content measured by hand: its getScrollElement(), its .inner-scroll or its part="scroll"', () => {
    const copy = [
      'return page.evaluate(async () => {',
      "  const content = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-content') as",
      '    | (HTMLElement & { getScrollElement?: () => Promise<HTMLElement> })',
      '    | null;',
      '  const inner = content?.getScrollElement ? await content.getScrollElement() : null;',
      '  return inner ? inner.scrollWidth - window.innerWidth : 0;',
      '});',
    ];
    expect(documentMeasures('b.ts', copy.join('\n'))).toEqual(['b.ts:6']);
    expect(documentMeasures('b.ts', 'return (await content.getScrollElement()).scrollWidth > innerWidth;')).toEqual(['b.ts:1']);
    const shadow = [
      "const scroll = shown.querySelector('ion-content')?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');",
      'if (scroll && scroll.scrollWidth > scroll.clientWidth + 1) found.push(scroll);',
    ];
    expect(documentMeasures('b.ts', shadow.join('\n'))).toEqual(['b.ts:2']);
    expect(documentMeasures('b.ts', `return content.shadowRoot?.querySelector('[part~="scroll"]')?.scrollWidth ?? 0;`)).toEqual(['b.ts:1']);
  });

  it('the count reads the root or a scroll box measured through `??` or `as` in line, a then() or a destructured scrollWidth', () => {
    const inline = [
      'return (document.scrollingElement ?? document.documentElement).scrollWidth - innerWidth;',
      'return (document.scrollingElement as HTMLElement | null)?.scrollWidth ?? 0;',
      'return content.getScrollElement().then((element) => element.scrollWidth - innerWidth);',
      'const { scrollWidth, clientWidth } = document.documentElement;',
      'const { scrollWidth } = await content.getScrollElement();',
      'const { documentElement: { scrollWidth } } = document;',
    ];
    expect(inline.map((line) => documentMeasures('d.ts', line))).toEqual(inline.map(() => ['d.ts:1']));
    const named = ['const root = window.document.documentElement;', 'const { scrollWidth } = root;', 'return root.scrollWidth;'];
    expect(documentMeasures('d.ts', named.join('\n'))).toEqual(['d.ts:2', 'd.ts:3']);
    expect(documentMeasures('d.ts', "const { scrollWidth, clientWidth } = document.querySelector('ion-title')!;")).toEqual([]);
  });

  it('the count leaves alone the vertical scroll of an ion-content and an element that is only put in the body', () => {
    const vertical = [
      "const content = document.querySelector('ion-content') as HTMLElement & { getScrollElement(): Promise<HTMLElement> };",
      'return (await content.getScrollElement()).scrollTop;',
      'const scroller = await (content as HTMLElement & { getScrollElement(): Promise<HTMLElement> }).getScrollElement();',
      'pageScrolls: scroller.scrollHeight > scroller.clientHeight + 1,',
      "const scroll = shown.querySelector('ion-content')?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');",
      'const end = scroll.getBoundingClientRect().bottom - parseFloat(getComputedStyle(scroll).paddingBottom);',
      `const box = element.shadowRoot?.querySelector('[part~="scroll"]')?.clientWidth ?? element.clientWidth;`,
    ];
    expect(documentMeasures('c.ts', vertical.join('\n'))).toEqual([]);
    const child = ['const element = document.body.appendChild(document.createElement(tag));', 'return element.scrollWidth;'];
    expect(documentMeasures('c.ts', child.join('\n'))).toEqual([]);
  });

  it('the count reads the width taken from the root, the root found by its selector or its locator, and a measure split over lines', () => {
    const copies = [
      ['const { scrollWidth, clientWidth } = document.documentElement;', 'return scrollWidth - clientWidth;'],
      ["const html = document.querySelector('html')!;", 'return html.scrollWidth - innerWidth;'],
      ["return document.querySelector('body')?.scrollWidth ?? 0;"],
      ["const overflow = await page.locator('html').evaluate((html) => html.scrollWidth - html.clientWidth);"],
      ["const wide = await page.$eval('body', (body) => body.scrollWidth > innerWidth);"],
      ['const { scrollWidth } = await content.getScrollElement();'],
      ['page.evaluate(() =>', '  document.documentElement', '    .scrollWidth - window.innerWidth)'],
      ['const overflow = await page', "  .locator(':root')", '  .evaluate((root) => root.scrollWidth - root.clientWidth);'],
    ];
    expect(copies.map((copy) => documentMeasures('d.ts', copy.join('\n')))).toEqual([
      ['d.ts:1'],
      ['d.ts:2'],
      ['d.ts:1'],
      ['d.ts:1'],
      ['d.ts:1'],
      ['d.ts:1'],
      ['d.ts:2'],
      ['d.ts:1'],
    ]);
    const none = [
      ['const { scrollWidth } = table;'],
      ['const { scrollHeight, clientHeight } = document.documentElement;'],
      ["await page.locator('body').press('Escape');"],
      ['const cut = await page', "  .locator('.label')", '  .evaluate((label) => label.scrollWidth > label.clientWidth);'],
    ];
    expect(none.map((lines) => documentMeasures('d.ts', lines.join('\n')))).toEqual(none.map(() => []));
  });

  it('the count reads a chain going on with `?.`, a typed selector, a root named over lines or with no semicolon, and keeps a spread or a statement after a locator apart', () => {
    const copies = [
      ["return document.querySelector('html')", '  ?.scrollWidth ?? 0;'],
      ["return document.querySelector<HTMLElement>('html')!.scrollWidth - innerWidth;"],
      ['const root = document', '  .documentElement;', 'return root.scrollWidth;'],
      ['const { documentElement: html } = document', 'return html.scrollWidth'],
      ['const widths = [0,', '  ...[document.documentElement.scrollWidth]];'],
    ];
    expect(copies.map((copy) => documentMeasures('e.ts', copy.join('\n')))).toEqual([
      ['e.ts:1'],
      ['e.ts:1'],
      ['e.ts:3'],
      ['e.ts:2'],
      ['e.ts:2'],
    ]);
    const after = "await page.locator('body').press('End'); const cut = await title.evaluate((el) => el.scrollWidth > el.clientWidth);";
    expect(documentMeasures('e.ts', after)).toEqual([]);
  });
});
