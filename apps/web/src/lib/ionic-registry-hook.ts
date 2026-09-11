// The shell's single hook on `customElements.define`.
//
// Two things the shell has to get right about Ionic cannot be done from the outside, because the
// controls a merchant actually types into are rendered by module Web Components — foreign bundles,
// from 27 separate repos, inside their own shadow roots:
//
//   · `fill` must paint a box (hub#1060 → `./ionic-fill`);
//   · the buttons of the selection dialogs must speak the user's language (hub#1736 →
//     `./ionic-select-text`).
//
// Both need the SAME hook, and for the same three reasons (the long version is in `./ionic-fill`):
// a document stylesheet cannot cross a shadow boundary, a MutationObserver fires after the element
// is already connected, and patching a prototype AFTER `customElements.define` is a silent no-op —
// the HTML spec captures a custom element's lifecycle callbacks inside `define`. Wrapping `define`
// is the only place that is early enough and works on the element itself.
//
// It lives in its own module so there is exactly ONE wrapper around the registry: two features
// wrapping `define` independently works, but the third one that forgets to chain the previous
// `define` silently disables the other two, and nothing would throw.

/** Runs on the element class the instant before it is registered, never after. */
export type CustomElementPatch = (ctor: CustomElementConstructor) => void;

/** Holds, on the registry, the patches to apply per tag. */
const PATCHES = Symbol.for('erplora.ionic-registry.patches');
/** Marks the registry whose `define` we already wrapped. */
const WRAPPED = Symbol.for('erplora.ionic-registry.wrapped');

type PatchesByTag = Map<string, CustomElementPatch[]>;

/**
 * Applies `patch` to `tags` the moment each of them is registered.
 *
 * Returns the tags that were **already** registered when this was called — for those the patch can
 * no longer be installed, and the failure is invisible by nature (the control simply renders
 * wrong), so every caller reports it. Ordering is the whole fix: this has to run before
 * `@ionic/vue` is imported, which is why the callers are side-effect `*.boot` modules imported at
 * the very top of `main.ts`.
 */
export function patchIonicOnDefine(
  tags: readonly string[],
  patch: CustomElementPatch,
): readonly string[] {
  const registry = globalThis.customElements;
  if (!registry) return []; // SSR / unit tests without a DOM: nothing to hook.

  const patches = ((registry as unknown as Record<symbol, PatchesByTag>)[PATCHES] ??= new Map());
  for (const tag of tags) {
    const forTag = patches.get(tag) ?? [];
    // Booting twice must not run the same patch twice; a second, different patch is welcome.
    if (!forTag.includes(patch)) forTag.push(patch);
    patches.set(tag, forTag);
  }

  if (!Object.prototype.hasOwnProperty.call(registry, WRAPPED)) {
    Object.defineProperty(registry, WRAPPED, { value: true, enumerable: false });
    const original = registry.define.bind(registry);
    registry.define = (
      name: string,
      ctor: CustomElementConstructor,
      options?: ElementDefinitionOptions,
    ) => {
      for (const apply of patches.get(name) ?? []) {
        try {
          apply(ctor);
        } catch (error) {
          // A broken patch must not take the element down with it: an `ion-select` that is never
          // registered renders as an unknown tag — a blank spot where a control should be.
          console.error(`[ionic-registry] patching <${name}> failed; registering it unpatched`, error);
        }
      }
      return original(name, ctor, options);
    };
  }

  return tags.filter((tag) => registry.get(tag));
}
