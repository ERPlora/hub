// A paper printed inside the installed app (hub#455; ERPlora/app hub#2006, hub#2008): the app's webview prints
// nothing on `window.print()`, so the paper goes to the app's own print screen — the `print_document` command, which
// takes a whole HTML document and opens the system's print dialog with it (a printer or «Save as PDF»: Android's
// PrintManager, the desktop's print window). In a browser nothing changes: the caller opens the browser's dialog.
//
// The document stands on its own, because the window that prints it runs no script, allows no stylesheet and has no
// address of the hub (CSP `default-src 'none'; style-src 'unsafe-inline'; img-src data: blob: https:;
// font-src data: https:`): the paper's own markup, the page's CSS rules that dress the paper (inline, in one
// `<style>`) and its images at their full address. It is a string read from the DOM (`outerHTML`, `cssText`), never
// written back into the page, so Trusted Types have nothing to say.
import { nativeBridge } from '@erplora/ui/shell';

/** The app's command for the system's print screen (ERPlora/app `src-tauri/src/lib.rs`). */
export const PRINT_DOCUMENT_COMMAND = 'print_document';

/** Where the app has no print screen (iOS): the browser's dialog is the way. */
const UNSUPPORTED = 'native_print_unsupported';

/** Why the app did not open its print screen; each one is a sentence under `base.print.refusal`. */
export type PrintRefusalReason = 'refused' | 'failed' | 'unlinked' | 'outdated';

/** The app refused to print: `reason` is what the person is told, `detail` what the app answered. */
export class PrintRefused extends Error {
  constructor(
    readonly reason: PrintRefusalReason,
    readonly detail: unknown,
  ) {
    super(`print_document: ${reason}`);
    this.name = 'PrintRefused';
  }
}

export interface PaperDocumentOptions {
  /** The document's title: the print job's name, and the file name «Save as PDF» proposes. */
  title: string;
  /** The paper's language (`<html lang>`); the page's when not given. */
  lang?: string;
  /** Rules of a paper whose styles do not live in a stylesheet of the page. */
  css?: string;
}

type Translate = (key: string) => string;

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
const escapeText = (text: string) => text.replace(/[&<>"]/g, (c) => ESCAPES[c]);

/** Pseudo-elements: `.paper::after` dresses the paper, but no element matches it as written. */
const PSEUDO_ELEMENT = /::?(?:before|after|first-line|first-letter|marker|placeholder|selection|backdrop)\b/g;

function dresses(paper: Element, selector: string): boolean {
  const bare = selector.replace(PSEUDO_ELEMENT, '');
  try {
    return paper.matches(bare) || paper.querySelector(bare) !== null;
  } catch {
    return false;
  }
}

/** The rules of `rules` that style `paper` or something inside it, `@media`, `@supports` and `@layer` kept. */
function rulesFor(rules: CSSRuleList, paper: Element): string[] {
  const kept: string[] = [];
  for (const rule of Array.from(rules)) {
    if ('selectorText' in rule && typeof rule.selectorText === 'string') {
      if (dresses(paper, rule.selectorText)) kept.push(rule.cssText);
      continue;
    }
    const group = rule as CSSGroupingRule & { conditionText?: string; name?: string };
    if (!group.cssRules) continue;
    const inner = rulesFor(group.cssRules, paper);
    if (inner.length === 0) continue;
    const head = rule.cssText.slice(0, rule.cssText.indexOf('{')).trim();
    kept.push(`${head} { ${inner.join(' ')} }`);
  }
  return kept;
}

function paperStyles(paper: Element, doc: Document): string[] {
  const kept: string[] = [];
  for (const sheet of Array.from(doc.styleSheets)) {
    let rules: CSSRuleList;
    try {
      rules = sheet.cssRules;
    } catch {
      // A stylesheet of another origin cannot be read; the hub serves its own.
      continue;
    }
    kept.push(...rulesFor(rules, paper));
  }
  return kept;
}

/** The paper as a whole HTML page of its own: what `print_document` prints. The paper on screen is not touched. */
export function paperDocument(paper: HTMLElement, options: PaperDocumentOptions, doc: Document = document): string {
  const copy = paper.cloneNode(true) as HTMLElement;
  const originals = paper.querySelectorAll('img');
  copy.querySelectorAll('img').forEach((img, index) => {
    const original = originals[index];
    const src = original.currentSrc || original.src;
    if (src) img.setAttribute('src', src);
    img.removeAttribute('srcset');
    // Offscreen, a lazy image would never load.
    img.removeAttribute('loading');
  });
  const css = [...paperStyles(paper, doc), options.css ?? '', 'html, body { margin: 0; background: #fff; }']
    .filter(Boolean)
    .join('\n')
    // A `</style` inside a rule would close the element: `\/` is the same character to CSS.
    .replace(/<\/(style)/gi, '<\\/$1');
  const lang = options.lang ?? doc.documentElement.lang;
  return [
    '<!doctype html>',
    lang ? `<html lang="${escapeText(lang)}">` : '<html>',
    '<head>',
    '<meta charset="utf-8">',
    `<title>${escapeText(options.title)}</title>`,
    `<style>${css}</style>`,
    '</head>',
    `<body>${copy.outerHTML}</body>`,
    '</html>',
  ].join('');
}

function reasonOf(answer: string): PrintRefusalReason {
  if (answer === 'print_document_refused') return 'refused';
  if (answer === 'not_the_linked_hub') return 'unlinked';
  // An app from before the command (Tauri's own answers: the ACL knows no such permission, or no such command).
  if (/not found|not allowed/i.test(answer)) return 'outdated';
  return 'failed';
}

/**
 * Inside the installed app, opens the system's print screen with `paper` alone and resolves `true`. Resolves `false`
 * where there is no app (a browser) or the app has no print screen on this system: the browser's dialog is the way.
 * Rejects with `PrintRefused` when the app refused, with the reason the person is told.
 */
export async function printInTheApp(paper: HTMLElement, options: PaperDocumentOptions, win: object = window): Promise<boolean> {
  const bridge = nativeBridge(win);
  if (!bridge) return false;
  try {
    await bridge.invoke(PRINT_DOCUMENT_COMMAND, { html: paperDocument(paper, options) });
    return true;
  } catch (error) {
    const answer = error instanceof Error ? error.message : String(error);
    if (answer === UNSUPPORTED) return false;
    console.error('hub: print_document refused', error);
    throw new PrintRefused(reasonOf(answer), error);
  }
}

/** The reason of a refusal of the app, in the reader's language; `null` for anything else (the browser's). */
export function printRefusal(error: unknown, t: Translate): string | null {
  return error instanceof PrintRefused ? t(`base.print.refusal.${error.reason}`) : null;
}

/** «<failure>: <reason>», or the failure alone without a reason. */
export function withReason(failure: string, reason: string | null): string {
  return reason ? `${failure.replace(/\.\s*$/, '')}: ${reason}` : failure;
}
