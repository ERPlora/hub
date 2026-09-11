// Side-effect module, imported by `main.ts` before `@ionic/vue` — see `./ionic-select-text` for
// the why.
//
// It cannot be a call in main.ts's body: ES modules evaluate every `import` before the first
// statement of the importing module, and `@ionic/vue` registers `ion-select` on import
// (`defineContainer()` → `defineCustomElement()`). By then the custom element definition is frozen
// — the HTML spec captures its lifecycle callbacks inside `customElements.define` — and there is
// nothing left to hook. Import order IS the fix.
import { bootIonicSelectText } from './ionic-select-text';

bootIonicSelectText();
