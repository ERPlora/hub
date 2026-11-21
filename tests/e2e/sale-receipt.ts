// A sale's receipt paper as laid out on screen (`ReceiptPaper.vue`): where its number and its date and time sit.
import type { Locator } from '@playwright/test';

/** Where the number and the date and time sit on `paper`: how many lines each takes, whether the date shares the
 *  number's line (after it) or starts right under it, and how far any of them runs past the paper's printable width. */
export interface NumberRow {
  numberLines: number;
  dateLines: number;
  dateBeside: boolean;
  dateUnder: boolean;
  overflow: number;
}

export async function numberRow(paper: Locator): Promise<NumberRow> {
  return paper.evaluate((el) => {
    const style = getComputedStyle(el);
    const right = el.getBoundingClientRect().right - parseFloat(style.paddingRight);
    const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
    /** The text boxes of `node`, one per piece of a line it wraps onto. */
    const boxes = (node: Element) => {
      const range = document.createRange();
      range.selectNodeContents(node);
      return [...range.getClientRects()].filter((box) => box.width > 0 && box.height > 0);
    };
    /** How many lines `node`'s text takes: its boxes grouped by their top, half a line apart. */
    const lines = (node: Element) => {
      const tops = boxes(node).map((box) => box.top).sort((a, b) => a - b);
      return tops.filter((top, index) => index === 0 || top - tops[index - 1] > lineHeight / 2).length;
    };
    const number = el.querySelector('[data-testid=sale-receipt-number]')!;
    const date = el.querySelector('[data-testid=sale-receipt-datetime]')!;
    const numberBoxes = boxes(number);
    const dateBoxes = boxes(date);
    const numberTop = Math.min(...numberBoxes.map((box) => box.top));
    const numberRight = Math.max(...numberBoxes.map((box) => box.right));
    const dateTop = Math.min(...dateBoxes.map((box) => box.top));
    const dateLeft = Math.min(...dateBoxes.map((box) => box.left));
    const dateRight = Math.max(...dateBoxes.map((box) => box.right));
    // How far the date's text is from the number's, against the height of a line. Both are set in the same font, so its
    // text box cancels out: between text boxes, a box is as tall as the machine's font says, and `ReceiptPaper.vue` asks
    // for a font the Hub does not serve (hub#731: 3.5 px of nothing on a Mac, with no blank line on the paper). The boxes
    // of the two flex items would not do either: they touch with padding inside them or a row that stretches them.
    const dateStyle = getComputedStyle(date);
    const dateFontSize = parseFloat(dateStyle.fontSize);
    const dateLineHeight = parseFloat(dateStyle.lineHeight) || dateFontSize * 1.2;
    const lineGap = dateTop - Math.max(...numberBoxes.map((box) => box.top)) - dateLineHeight;
    return {
      numberLines: lines(number),
      dateLines: lines(date),
      dateBeside: Math.abs(dateTop - numberTop) < lineHeight / 2 && dateLeft >= numberRight,
      // Right under it, as the next line of the paper: no blank line between them, not even inside a line twice the font.
      dateUnder: lineGap >= -1 && lineGap <= 2 && dateLineHeight < 2 * dateFontSize,
      // Whole pixels: text set flush right lands a hundredth of a pixel either side of the edge.
      overflow: Math.max(0, Math.round(Math.max(numberRight, dateRight) - right)),
    };
  });
}
