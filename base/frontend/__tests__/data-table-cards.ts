// What the cards of a DataTable show, read as a person reads them: the value beside a field's label.
import type { DOMWrapper } from '@vue/test-utils';

/** The values the cards show beside `label`, card by card. */
export function cardValues(wrapper: { findAll: (selector: string) => DOMWrapper<Element>[] }, label: string): string[] {
  return wrapper
    .findAll('.data-table__card-meta')
    .filter((field) => field.find('.data-table__card-meta-label').text() === label)
    .map((field) => field.find('.data-table__card-meta-value').text().trim());
}
