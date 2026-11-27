// What a button that is only its icon shows: no text, its label as the name a screen reader hears and as the title on
// hover, and its icon in Ionic's `icon-only` slot, which is what gives it the common square to hit.
import type { DOMWrapper } from '@vue/test-utils';

import { accessibleName } from './mount-base';

export interface IconOnly {
  shown: string;
  name: string | null | undefined;
  title: string | undefined;
  slot: boolean;
}

/** A button as `find`, `get` or `new DOMWrapper(…)` give it. */
type Button = Pick<DOMWrapper<Element>, 'text' | 'element' | 'attributes' | 'find'>;

export function iconOnly(button: Button): IconOnly {
  return {
    shown: button.text().trim(),
    name: accessibleName(button.element),
    title: button.attributes('title'),
    slot: button.find('[slot="icon-only"]').exists(),
  };
}

/** The same, for a button whose label is `label`. */
export const iconOnlyNamed = (label: string): IconOnly => ({ shown: '', name: label, title: label, slot: true });
