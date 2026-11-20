import type { AllergenCode } from '@erplora/ui/components';

import type { OrderOut } from '../operations';

declare module '../operations' {
  interface OrderLineOut {
    allergens: AllergenCode[];
    allergy: AllergenCode[];
    allergy_in_dish: AllergenCode[];
  }

  interface ComboDishOut {
    allergens: AllergenCode[];
    allergy_in_dish: AllergenCode[];
  }
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'sale.order.set_line_allergy': {
      input: { order_id: string; line_id: string; allergy: AllergenCode[] };
      output: OrderOut;
    };
  }
}
