// Registra los Web Components de @ionic/core que los componentes de OutfitKit (ok-*) usan POR
// DENTRO, pero que quizá ninguna SFC importa directamente vía @ionic/vue. Necesario porque
// ok-data-table/ok-modal/etc. asumen que el HOST registró sus ion-* (convención de OutfitKit).
// `defineCustomElement` standalone es idempotente (comprueba customElements.get antes de define),
// así que no choca con los registros de @ionic/vue. CSP-safe (ESM estático, sin eval).
import { defineCustomElement as ionButton } from '@ionic/core/components/ion-button.js';
import { defineCustomElement as ionIcon } from '@ionic/core/components/ion-icon.js';
import { defineCustomElement as ionInput } from '@ionic/core/components/ion-input.js';
import { defineCustomElement as ionSearchbar } from '@ionic/core/components/ion-searchbar.js';
import { defineCustomElement as ionSelect } from '@ionic/core/components/ion-select.js';
import { defineCustomElement as ionSelectOption } from '@ionic/core/components/ion-select-option.js';
import { defineCustomElement as ionModal } from '@ionic/core/components/ion-modal.js';
import { defineCustomElement as ionActionSheet } from '@ionic/core/components/ion-action-sheet.js';
import { defineCustomElement as ionToast } from '@ionic/core/components/ion-toast.js';
import { defineCustomElement as ionAlert } from '@ionic/core/components/ion-alert.js';
// ion-checkbox → selección múltiple de ok-data-table (selectable). ion-toggle/ion-reorder(-group)/
// ion-chip → modal "Personalizar panel" de ok-widget-board (raw DOM, no los importa ninguna SFC).
import { defineCustomElement as ionCheckbox } from '@ionic/core/components/ion-checkbox.js';
import { defineCustomElement as ionToggle } from '@ionic/core/components/ion-toggle.js';
import { defineCustomElement as ionReorder } from '@ionic/core/components/ion-reorder.js';
import { defineCustomElement as ionReorderGroup } from '@ionic/core/components/ion-reorder-group.js';
import { defineCustomElement as ionChip } from '@ionic/core/components/ion-chip.js';

export function registerOutfitkitIonicDeps(): void {
  [
    ionButton, ionIcon, ionInput, ionSearchbar, ionSelect, ionSelectOption,
    ionModal, ionActionSheet, ionToast, ionAlert,
    ionCheckbox, ionToggle, ionReorder, ionReorderGroup, ionChip,
  ].forEach((def) => def());
}
