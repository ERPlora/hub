// The labels of a form's fields: which of them do not fit their box.
import type { Locator } from '@playwright/test';

/** The fields of `form` whose label does not fit and is cut with «…» (none should be). */
export async function cutLabels(form: Locator): Promise<string[]> {
  return form.locator('ion-input, ion-select, ion-textarea').evaluateAll((fields) =>
    fields.flatMap((field) => {
      const label = field.shadowRoot?.querySelector('.label-text') ?? field.querySelector('.label-text');
      return label && label.scrollWidth > label.clientWidth ? [field.getAttribute('data-testid') ?? field.tagName] : [];
    }),
  );
}
