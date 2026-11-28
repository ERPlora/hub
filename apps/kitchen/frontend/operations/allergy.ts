import type { AllergenCode } from '@erplora/ui/components';

declare module './tickets' {
  interface ItemOut {
    allergy: AllergenCode[];
    allergy_in_dish: AllergenCode[];
  }
}
