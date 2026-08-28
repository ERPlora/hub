// How much room the shell has — read ONCE, here, so every chrome that has to fold on a phone folds
// at the same width.
//
// This exists because of the topbar. Ionic centres `ion-title` in `ios` mode, so the actions of the
// `end` slot do not push the title aside: they sit on top of it. On a 390px till the name of the
// screen was unreadable behind four icon-only buttons (reported 2026-08-09), and below the tablet
// step they collapse into one overflow menu.
//
// It is a REACTIVE value and not a media query in the stylesheet on purpose: what changes below the
// threshold is not how the buttons look, it is that they stop being buttons and become rows of a
// menu. `display:none` would have been one CSS line and would have left every hidden control in the
// tab order and announced to a screen reader — two copies of each action, one of them invisible.
import { computed, ref, type ComputedRef } from 'vue';

/**
 * The width at which the toolbar runs out of room, = Ionic's own `md` step.
 *
 * From a tablet up the title and the global actions fit side by side, which is also where Ionic
 * itself stops treating the layout as a phone.
 */
export const COMPACT_VIEWPORT_QUERY = '(max-width: 767px)';

const _compact = ref<boolean>(false);

/** `true` while the screen is too narrow to sit the global actions beside the title. */
export const isCompactViewport: ComputedRef<boolean> = computed(() => _compact.value);

/**
 * The width at which the panel's two setup cards fold (hub#1197) — «My apps» and the setup
 * checklist. Narrower than {@link COMPACT_VIEWPORT_QUERY}: the topbar runs out of room a full
 * tablet step before a card's grid/rows do, and folding both at 767px would cost a tablet its full
 * checklist for no width reason. 540px is not invented for this: it is the breakpoint the setup
 * card's own stylesheet already used for its footer button.
 */
export const PHONE_VIEWPORT_QUERY = '(max-width: 540px)';

const _phone = ref<boolean>(false);

/** `true` while the screen is too narrow for the panel's cards to show everything at once. */
export const isPhoneViewport: ComputedRef<boolean> = computed(() => _phone.value);

// Bound at load, not on the first render: a topbar that painted its buttons and then swapped them
// for a menu would flash on every boot of the till — and the same is true of a card that paints
// every row and then folds most of them away a frame later.
if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  const compactMql = window.matchMedia(COMPACT_VIEWPORT_QUERY);
  _compact.value = compactMql.matches;
  compactMql.addEventListener('change', (event) => {
    _compact.value = event.matches;
  });

  const phoneMql = window.matchMedia(PHONE_VIEWPORT_QUERY);
  _phone.value = phoneMql.matches;
  phoneMql.addEventListener('change', (event) => {
    _phone.value = event.matches;
  });
}
