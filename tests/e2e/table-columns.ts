// How a DataTable list shares its width: what it paints column by column, read from the page.
import { expect, type Locator } from '@playwright/test';

/** What the list paints, column by column: its width, how far its cells drift from its header (px), the texts
 *  it cuts (header label included) and the room its cells leave beside their text (px; negative = cut). */
export interface Column {
  label: string;
  width: number;
  drift: number;
  cut: string[];
  room: number;
}
export interface Painted {
  /** px the list scrolls sideways (0 = none). */
  overflow: number;
  columns: Column[];
}

async function painted(table: Locator): Promise<Painted> {
  return table.evaluate((root) => {
    const scroll = root.querySelector('.data-table__scroll') as HTMLElement;
    const head = root.querySelector('.data-table__row--head') as HTMLElement;
    const headers = [...head.querySelectorAll<HTMLElement>(':scope > [role=columnheader]')];
    const rows = [...root.querySelectorAll<HTMLElement>('.data-table__row--data')];
    const columns = headers.map((header, index) => {
      const own = header.getBoundingClientRect();
      const cut: string[] = [];
      const label = header.querySelector<HTMLElement>(':scope > span');
      if (label && label.scrollWidth > label.clientWidth) cut.push(`header ${label.textContent?.trim()}`);
      let drift = 0;
      let room = Infinity;
      for (const row of rows) {
        const cell = row.querySelectorAll<HTMLElement>(':scope > [role=cell]')[index];
        const box = cell.getBoundingClientRect();
        drift = Math.max(drift, Math.abs(box.left - own.left), Math.abs(box.right - own.right));
        for (const span of cell.querySelectorAll<HTMLElement>(':scope > span')) {
          if (span.scrollWidth > span.clientWidth) cut.push(span.textContent?.trim() ?? '');
          const style = getComputedStyle(cell);
          const inside = cell.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
          room = Math.min(room, inside - span.scrollWidth);
        }
      }
      return {
        label: header.textContent?.trim() ?? '',
        width: Math.round(own.width * 10) / 10,
        drift: Math.round(drift * 10) / 10,
        cut,
        room: Number.isFinite(room) ? Math.round(room) : 0,
      };
    });
    return { overflow: scroll.scrollWidth - scroll.clientWidth, columns };
  });
}

/** `painted` once two readings in a row agree: the list settles on its own resize in a few frames. */
export async function steady(table: Locator): Promise<Painted> {
  let seen: Painted | undefined;
  let last = '';
  await expect
    .poll(async () => {
      seen = await painted(table);
      const now = JSON.stringify(seen);
      const same = now === last;
      last = now;
      return same;
    })
    .toBe(true);
  return seen!;
}
