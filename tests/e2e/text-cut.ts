// What a person cannot read whole on the page as it is painted now (text-cut.spec.ts pins each case):
// - Cut: part of a text lies inside a box whose overflow is hidden or clip and part past its edge (more than 2 px
//   across, more than a third of a line down), with no «…» to say there is more. Wholly past the edge is hidden on
//   purpose (a folded panel, a slide away); a box of 1 px or less is the screen reader's text. A box that scrolls on
//   an axis frees the text on that axis: the person scrolls to it.
// - Ellipsis: the box that cuts is the text's own block with `text-overflow: ellipsis`, or its line clamp cuts the
//   lines, and nothing gives the text whole: no `title` around it that holds it, and it is not the value an
//   `ion-select` shows (opening it shows the options whole).
// - Split word: a run of 2 to 12 letters, in a token of at most 16 characters, over two lines (a long token such as an
//   address may break anywhere; so may a box with `word-break: break-all`, `line-break: anywhere` or `hyphens: auto`).
import type { Page } from '@playwright/test';

export interface CutText {
  kind: 'cut' | 'ellipsis' | 'split-word';
  /** The box that cuts it (or the block that splits the word), through the web components that hold it. */
  box: string;
  /** The text as written, whole (the word, for a split one). */
  text: string;
}

/** Every text of the page that a person cannot read whole, once per box and text. */
export function cutTexts(page: Page): Promise<CutText[]> {
  return page.evaluate(scan);
}

/** Runs in the page: it can only use what it declares. */
function scan(): CutText[] {
  interface Edges {
    l: number;
    t: number;
    r: number;
    b: number;
  }
  const styles = new Map<Element, CSSStyleDeclaration>();
  const style = (el: Element): CSSStyleDeclaration => {
    let cs = styles.get(el);
    if (!cs) {
      cs = getComputedStyle(el);
      styles.set(el, cs);
    }
    return cs;
  };
  const clips = (value: string): boolean => value === 'hidden' || value === 'clip';
  const scrolls = (value: string): boolean => value === 'auto' || value === 'scroll';
  const words = (text: string): string => text.replace(/\s+/g, ' ').trim();

  /** The node above `node` as painted: the slot it is assigned to, its parent, or the host of its shadow root. */
  const above = (node: Node): Element | null => {
    const slotted = (node as Element | Text).assignedSlot;
    if (slotted) return slotted;
    if (node.parentElement) return node.parentElement;
    const root = node.parentNode;
    return root instanceof ShadowRoot ? root.host : null;
  };
  const named = (el: Element): string => {
    const classes = [...el.classList].slice(0, 2);
    const id = el.id ? `#${el.id}` : classes.length ? `.${classes.join('.')}` : '';
    const testid = el.getAttribute('data-testid');
    return `${el.localName}${id}${testid ? `[data-testid=${testid}]` : ''}`;
  };
  const pathOf = (el: Element): string => {
    const names = [named(el)];
    for (let root = el.getRootNode(); root instanceof ShadowRoot; root = root.host.getRootNode()) names.unshift(named(root.host));
    return names.join(' >> ');
  };
  /** An element that lays its text in its parent's lines: inline, a slot or `display: contents`. */
  const flows = (el: Element): boolean => el.localName === 'slot' || ['inline', 'contents'].includes(style(el).display);
  /** The block whose lines hold `node`: up through inline elements, slots and `display: contents`. */
  const blockOf = (node: Node): Element | null => {
    let el = above(node);
    while (el && flows(el)) el = above(el);
    return el;
  };
  const edgesOf = (el: Element): Edges => {
    const r = el.getBoundingClientRect();
    const l = r.left + el.clientLeft;
    const t = r.top + el.clientTop;
    return { l, t, r: l + el.clientWidth, b: t + el.clientHeight };
  };
  const pastX = (rects: DOMRect[], box: Edges): boolean => rects.some((r) => r.left < box.l - 2 || r.right > box.r + 2);
  // A line's box is taller than its letters: a third of it past the edge is where the letters start to go.
  const pastY = (rects: DOMRect[], box: Edges): boolean =>
    rects.some((r) => Math.max(box.t - r.top, r.bottom - box.b) > Math.max(2, r.height / 3));
  const overlaps = (r: DOMRect, box: Edges, x: boolean, y: boolean): boolean =>
    (!x || (Math.min(r.right, box.r) - Math.max(r.left, box.l) > 1)) && (!y || (Math.min(r.bottom, box.b) - Math.max(r.top, box.t) > 1));
  const clamps = (cs: CSSStyleDeclaration): boolean => {
    const clamp = cs.getPropertyValue('-webkit-line-clamp');
    return !!clamp && clamp !== 'none' && cs.getPropertyValue('-webkit-box-orient') === 'vertical';
  };

  type Axes = { x: boolean; y: boolean };
  /** Marks free the axes on which `el` scrolls to the part of `rects` past its edge. */
  const freeIn = (cs: CSSStyleDeclaration, rects: DOMRect[], box: Edges, free: Axes): void => {
    if (scrolls(cs.overflowX) && pastX(rects, box)) free.x = true;
    if (scrolls(cs.overflowY) && pastY(rects, box)) free.y = true;
  };
  /** What `el` does to `rects`: lets them fit, hides them whole, or cuts them on some axes. */
  const verdictOf = (el: Element, rects: DOMRect[], free: Axes): 'fits' | 'hidden' | Axes => {
    const cs = style(el);
    const box = edgesOf(el);
    freeIn(cs, rects, box, free);
    const x = clips(cs.overflowX) && !free.x && pastX(rects, box);
    const y = clips(cs.overflowY) && !free.y && pastY(rects, box);
    if (!x && !y) return 'fits';
    const shows = el.clientWidth > 1 && el.clientHeight > 1 && rects.some((r) => overlaps(r, box, clips(cs.overflowX), clips(cs.overflowY)));
    return shows ? { x, y } : 'hidden';
  };
  /** The box that cuts `rects` and on which axes, or null: the first one, going up, that shows part and hides part. */
  const cutterOf = (node: Text, rects: DOMRect[]): ({ box: Element } & Axes) | null => {
    const free = { x: false, y: false };
    for (let el = above(node); el && el !== document.documentElement; el = above(el)) {
      if (flows(el)) continue;
      const verdict = verdictOf(el, rects, free);
      if (verdict === 'hidden') return null;
      if (verdict !== 'fits') return { box: el, ...verdict };
    }
    return null;
  };
  /** Whether the box draws its own «…» where it cuts the text. */
  const shortened = (node: Text, cut: { box: Element } & Axes): boolean => {
    const cs = style(cut.box);
    const own = blockOf(node) === cut.box;
    const dotsX = own && cs.textOverflow === 'ellipsis' && !/flex|grid/.test(cs.display);
    return (!cut.x || dotsX) && (!cut.y || clamps(cs));
  };
  /** Whether a text that ends in «…» is given whole: a title around it, or it is the value an ion-select shows. */
  const readable = (node: Text, text: string): boolean => {
    for (let el = above(node); el; el = above(el)) {
      if (words(el.getAttribute('title') ?? '').includes(text)) return true;
      const part = el.getAttribute('part') ?? '';
      const root = el.getRootNode();
      if (/\b(text|placeholder)\b/.test(part) && root instanceof ShadowRoot && root.host.localName === 'ion-select') return true;
    }
    return false;
  };

  const found = new Map<string, CutText>();
  const note = (cut: CutText): void => {
    found.set(`${cut.kind}|${cut.box}|${cut.text}`, cut);
  };
  const rectsOf = (range: Range): DOMRect[] => [...range.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5);
  const linesOf = (range: Range): number => new Set(rectsOf(range).map((r) => Math.round(r.top))).size;

  const measureCut = (node: Text, rects: DOMRect[]): void => {
    const cut = cutterOf(node, rects);
    if (!cut) return;
    const text = words(node.textContent ?? '');
    const dots = shortened(node, cut);
    if (dots && readable(node, text)) return;
    note({ kind: dots ? 'ellipsis' : 'cut', box: pathOf(cut.box), text });
  };
  const measureSplit = (node: Text, range: Range): void => {
    const block = blockOf(node);
    if (!block) return;
    const cs = style(block);
    if (cs.wordBreak === 'break-all' || cs.lineBreak === 'anywhere' || cs.hyphens === 'auto') return;
    const content = node.textContent ?? '';
    for (const token of content.matchAll(/\S+/g)) {
      if (token[0].length > 16) continue;
      for (const run of token[0].matchAll(/(?<![\p{L}\p{N}])[\p{L}\p{N}]{2,12}(?![\p{L}\p{N}])/gu)) {
        const at = (token.index ?? 0) + (run.index ?? 0);
        range.setStart(node, at);
        range.setEnd(node, at + run[0].length);
        if (linesOf(range) > 1) note({ kind: 'split-word', box: pathOf(block), text: run[0] });
      }
    }
  };
  const measure = (node: Text): void => {
    const holder = node.parentElement;
    if (!holder || ['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT'].includes(holder.tagName)) return;
    if (!words(node.textContent ?? '')) return;
    let painted: Element | null = holder;
    while (painted && style(painted).display === 'contents') painted = above(painted);
    if (!painted?.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return;
    const range = document.createRange();
    range.selectNodeContents(node);
    const rects = rectsOf(range);
    if (!rects.length) return;
    measureCut(node, rects);
    if (linesOf(range) > 1) measureSplit(node, range);
  };
  const walk = (root: Node): void => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let node: Node | null = walker.currentNode; node; node = walker.nextNode()) {
      if (node instanceof Text) measure(node);
      else if (node instanceof Element && node.shadowRoot) walk(node.shadowRoot);
    }
  };
  walk(document.body);
  return [...found.values()];
}
