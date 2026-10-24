// Ionic 8's `ion-searchbar` names its inner <input> with a constant, English `aria-label="search text"` (it inherits
// only `lang` and `dir` from its host), so a screen reader announced «search text» over a screen in Spanish. Stencil
// only rewrites that attribute when its own value changes, which it never does: setting it on the input survives
// re-renders. Base's own search boxes outside a DataTable (Files) call this after rendering and when the language
// changes; the DataTable of @erplora/ui names its box itself.

type Searchbar = Element & { getInputElement?: () => Promise<HTMLInputElement> };

/** Names the inner input of `bar` with `name()`, read once the input resolves (so a later language wins). */
export async function nameSearchbar(bar: Searchbar | null | undefined, name: () => string): Promise<void> {
  if (!bar) return;
  try {
    if (bar.localName === 'ion-searchbar') await customElements.whenDefined('ion-searchbar');
    const input = await bar.getInputElement?.();
    const text = name();
    if (input && input.getAttribute('aria-label') !== text) input.setAttribute('aria-label', text);
  } catch (error) {
    // A searchbar torn down meanwhile has nothing left to name; one still on screen would keep announcing «search
    // text», and that is a defect to see.
    if (bar.isConnected) console.error('[base] could not name the search box.', error);
  }
}
