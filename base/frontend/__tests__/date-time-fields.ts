// Picking in the date and time fields of @erplora/ui (DateField, TimeField) from a component test. Their picker,
// Ionic's calendar in a popover, only opens in a real browser (the e2e helper `tests/e2e/date-time-fields.ts` taps it
// there); here the field takes the value as its picker hands it over: the page's v-model hears it and the form around
// the field hears a native `input`, as FormModal listens for to take a refusal's mark away.
import { DateField, TimeField } from '@erplora/ui/components';
import type { ComponentInternalInstance } from 'vue';

import { settle } from './mount-in-shell';

const FIELDS = new Set<unknown>([DateField, TimeField]);

type Rendered = Element & { __vueParentComponent?: ComponentInternalInstance };

/** The DateField or TimeField whose ion-input is `el` (the element of its `data-testid`). */
function fieldOf(el: Element | null): ComponentInternalInstance {
  let instance = (el as Rendered | null)?.__vueParentComponent ?? null;
  while (instance && !FIELDS.has(instance.type)) instance = instance.parent;
  if (!instance) {
    const name = el?.getAttribute('data-testid') ?? 'nothing';
    throw new Error(`${name} is no date or time field (DateField, TimeField)`);
  }
  return instance;
}

/** Picks `value` (`YYYY-MM-DD` or `HH:MM`; '' as Clear) in the field whose ion-input is `el`. */
export async function pick(el: Element | null, value: string): Promise<void> {
  fieldOf(el).emit('update:modelValue', value);
  el?.dispatchEvent(new Event('input', { bubbles: true }));
  await settle();
}

/** What the field whose ion-input is `el` holds: its v-model, as the page sends it. */
export function picked(el: Element | null): string {
  return String(fieldOf(el).props.modelValue ?? '');
}
