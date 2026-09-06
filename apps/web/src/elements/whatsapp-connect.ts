// `<erp-whatsapp-connect>` — the «Connect WhatsApp» block as a custom element the WhatsApp module
// embeds in its settings screen (hub#1600, ADR-0452).
//
// Why an element and not a slot or an event: a module's Web Component may not load foreign
// scripts, and Meta's SDK is one; the shell may. Registering the block as a global element is the
// same mechanism by which modules already use `ok-*` and `ion-*` — nothing new in the contract.
// No shadow root: it lives inside the module's screen and takes the till's theme like everything
// else there; and the shell's i18n is installed on the element's own app so the sentences follow
// the till's language.
import { defineCustomElement } from 'vue';
import { i18n } from '../i18n';
import WhatsAppConnect from '../components/WhatsAppConnect.vue';

export const WHATSAPP_CONNECT_TAG = 'erp-whatsapp-connect';

/** Registers the element once; a second call (HMR, a second boot) is a no-op. */
export function registerWhatsAppConnectElement(registry: CustomElementRegistry = customElements): void {
  if (registry.get(WHATSAPP_CONNECT_TAG)) return;
  const element = defineCustomElement(WhatsAppConnect, {
    shadowRoot: false,
    configureApp(app) {
      app.use(i18n);
    },
  });
  registry.define(WHATSAPP_CONNECT_TAG, element);
}
