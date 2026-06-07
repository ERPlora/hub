// Registro idempotente de custom elements: evita "already defined" cuando un mismo tag
// puede cargarse por varias vías (shell + módulos + import-map). Cada componente llama
// a `define(tag, Class)` en lugar de `customElements.define` directamente.
export function define(tag: string, ctor: CustomElementConstructor): void {
  if (typeof customElements !== 'undefined' && !customElements.get(tag)) {
    customElements.define(tag, ctor);
  }
}
