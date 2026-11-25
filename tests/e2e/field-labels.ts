// The labels of a form's fields: which of them do not fit their box, and the room the raised ones have over them.
import { expect, type Locator } from '@playwright/test';

/** The fields of `form` whose label does not fit and is cut with «…» (none should be). */
export async function cutLabels(form: Locator): Promise<string[]> {
  return form.locator('ion-input, ion-select, ion-textarea').evaluateAll((fields) =>
    fields.flatMap((field) => {
      const label = field.shadowRoot?.querySelector('.label-text') ?? field.querySelector('.label-text');
      return label && label.scrollWidth > label.clientWidth ? [field.getAttribute('data-testid') ?? field.tagName] : [];
    }),
  );
}

/** How many px the raised label of `field` is under the box of `above`, a text or another field (under 0, on it). */
async function roomOverLabel(above: Locator, field: Locator): Promise<number> {
  const upper = await above.elementHandle();
  return field.evaluate((host, upper) => {
    const label = host.shadowRoot?.querySelector('.label-text') ?? host.querySelector('.label-text');
    if (!label || !upper) return NaN;
    return label.getBoundingClientRect().top - upper.getBoundingClientRect().bottom;
  }, upper);
}

/** The raised label of `field` is as far from the text over it as most forms put a label from the field over it: 14px
 *  between the boxes, less the 6px a label rises over its own. */
export async function expectTextClearOfLabel(text: Locator, field: Locator, where: string): Promise<void> {
  await expect.poll(() => roomOverLabel(text, field), { message: `${where}: the text and the label under it` }).toBeCloseTo(8.2, 0);
}

/** The raised label of `field` is at least as far from `above` as that, or as the label of `next` is from `field`. */
export async function expectRoomOverLabel(above: Locator, field: Locator, next: Locator | null, where: string): Promise<void> {
  const least = next ? await roomOverLabel(field, next) : 8;
  await expect.poll(() => roomOverLabel(above, field), { message: `${where}: the label and what is over it` }).toBeGreaterThanOrEqual(least);
}
