// How the browser laid out the words of a text on screen.
import type { Locator } from '@playwright/test';

/** Every word of the text right inside `target` that the browser drew over two lines (none when it breaks only
 *  between words). A word cut by an ellipsis stays on its line, though Chrome gives its hidden part a box of its own. */
export function splitWords(target: Locator): Promise<string[]> {
  return target.evaluate((el) => {
    const broken: string[] = [];
    for (const node of el.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE) continue;
      const text = node as Text;
      for (const match of text.data.matchAll(/\S+/g)) {
        const start = match.index ?? 0;
        const range = document.createRange();
        range.setStart(text, start);
        range.setEnd(text, start + match[0].length);
        const lines = new Set([...range.getClientRects()].map((box) => Math.round(box.top)));
        if (lines.size > 1) broken.push(match[0]);
      }
    }
    return broken;
  });
}
