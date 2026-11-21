import type { AllergenCode } from '@erplora/ui/components';

declare module '../operations' {
  interface ItemOut {
    allergy: AllergenCode[];
    allergy_in_dish: AllergenCode[];
  }
}
