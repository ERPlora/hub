// What the cards of a DataTable show, read as a person reads them: the value beside a field's label, or the icon of each line.
import type { DOMWrapper } from '@vue/test-utils';

/** The values the cards show beside `label`, card by card. */
export function cardValues(wrapper: { findAll: (selector: string) => DOMWrapper<Element>[] }, label: string): string[] {
  return wrapper
    .findAll('.data-table__card-meta')
    .filter((field) => field.find('.data-table__card-meta-label').text() === label)
    .map((field) => field.find('.data-table__card-meta-value').text().trim());
}

/** Each line of a card by its column, with the icon that tells what it is (`null` when the line has none). Once
 *  Ionic defines `ion-icon`, Vue hands it the name as a property instead of an attribute. */
export function cardIcons(card: Pick<DOMWrapper<Element>, 'findAll'>): Record<string, string | null> {
  return Object.fromEntries(
    card.findAll('.data-table__card-meta').map((line) => {
      const icon = line.find('.data-table__card-meta-icon');
      const name = icon.exists() ? ((icon.element as Element & { name?: string }).name ?? icon.attributes('name')) : undefined;
      return [line.attributes('data-column'), name ?? null];
    }),
  );
}

/** Turns the DataTable `testid` to its cards with its own list/cards switch, as a person does. */
export function switchToCards(wrapper: { get: (selector: string) => Pick<DOMWrapper<Element>, 'element'> }, testid: string): void {
  const view = wrapper.get(`[data-testid="${testid}-view"]`).element;
  view.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'cards' }, bubbles: true }));
}
