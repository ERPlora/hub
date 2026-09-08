// `<erp-whatsapp-connect>` — the «Connect WhatsApp» block as a custom element the WhatsApp module
// embeds in its settings screen (hub#1600, ADR-0452).
//
// Why an element and not a slot or an event: a module's Web Component may not load foreign
// scripts, and Meta's SDK is one; the shell may. Registering the block as a global element is the
// same mechanism by which modules already use `ok-*` and `ion-*` — nothing new in the contract.
// No shadow root: it lives inside the module's screen and takes the till's theme like everything
// else there.
//
// A custom element is its own island, though, and that island gets none of the shell's globals for
// free. Two of them have to be handed over by hand, and both are invisible until the block is
// actually embedded — which is why hub#1614 found them on the FIRST screen the owner sees:
//
//   * **Its sentences.** `useI18n()` in a web component looks the instance up under
//     `I18nInjectionKey`, not under the private symbol `app.use(i18n)` provides, so without the
//     explicit `provide` every sentence throws in setup and the owner is left staring at an empty
//     box where the «Connect» button should be.
//   * **Its looks.** Vue only injects an SFC's styles into a shadow root, so with none of its own
//     Vite sends `<style scoped>` to the shell's GLOBAL stylesheet — and a global stylesheet does
//     not cross into the shadow root of the module's screen, which is where this element lives.
//     The rules travel with the element instead, as a `<style>` in its own tree, written against
//     the tag so nothing else in the module's screen is repainted.
import { defineCustomElement } from 'vue';
import { I18nInjectionKey } from 'vue-i18n';
import { i18n } from '../i18n';
import WhatsAppConnect from '../components/WhatsAppConnect.vue';

export const WHATSAPP_CONNECT_TAG = 'erp-whatsapp-connect';

/**
 * The block's own rules, the single source for them (the SFC deliberately carries no `<style>`).
 *
 * Every selector is rooted at the tag: the `<style>` node lands in whatever tree the element is
 * in — the module's shadow root, normally — and there it would otherwise be free to repaint the
 * module's own markup. Colours fall back to plain values so the block is still readable on a host
 * that never set the `--ion-*` tokens.
 */
export const WHATSAPP_CONNECT_STYLES = `
${WHATSAPP_CONNECT_TAG} {
  display: block;
}
${WHATSAPP_CONNECT_TAG} .whatsapp-connect {
  display: grid;
  gap: 0.5rem;
}
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__number {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__identity {
  display: grid;
  gap: 0.25rem;
}
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__phone {
  font-variant-numeric: tabular-nums;
}
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__badges {
  display: inline-flex;
  gap: 0.375rem;
}
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__intro,
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__help,
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__admin-only,
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__status {
  margin: 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium, #6b7280);
}
${WHATSAPP_CONNECT_TAG} .whatsapp-connect__status--error {
  color: var(--ion-color-danger, #b91c1c);
}
`;

/** Marks the `<style>` this element owns, so a re-connect finds it instead of adding a second. */
const STYLE_MARKER = 'data-whatsapp-connect-styles';

/** Registers the element once; a second call (HMR, a second boot) is a no-op. */
export function registerWhatsAppConnectElement(registry: CustomElementRegistry = customElements): void {
  if (registry.get(WHATSAPP_CONNECT_TAG)) return;
  const VueBlock = defineCustomElement(WhatsAppConnect, {
    shadowRoot: false,
    configureApp(app) {
      // `use` for the rest of the app surface, `provide` for `useI18n()` — see the note on top:
      // in a web component the composition API reads the instance off `I18nInjectionKey` alone.
      app.use(i18n);
      app.provide(I18nInjectionKey, i18n);
    },
  });

  registry.define(
    WHATSAPP_CONNECT_TAG,
    class WhatsAppConnectElement extends VueBlock {
      connectedCallback(): void {
        // After Vue's, never before: on the first connect Vue moves every child of the element
        // into its slots, so a `<style>` put there first would be swallowed whole.
        super.connectedCallback();
        if (this.querySelector(`style[${STYLE_MARKER}]`)) return;
        const style = document.createElement('style');
        style.setAttribute(STYLE_MARKER, '');
        style.textContent = WHATSAPP_CONNECT_STYLES;
        this.appendChild(style);
      }
    },
  );
}
