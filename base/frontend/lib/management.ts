// «erplora.com» of the bar (BASE-F11; the old hub's `management-link.ts`, gh:hub#364): which copy of the Hub may offer
// the way to this business on erplora.com's panel. Who may (the permission) and how they entered (never with a PIN)
// the server already decided: it embeds the address only then (`hub-home`'s `manage_url`, `base/spa.py`).
//
// The cut is the DISTRIBUTION, not the operating system (gh:hub#1897): the panel is next door to the page that charges,
// three taps from the till, so the Google Play copy never shows it; a browser and the other copies of the app do. A
// browser is known from the first frame; the installed app says where its binary came from (`device_context`'s
// `distribution`: `play`, `msstore` or `direct`), and until it answers nothing is shown, so a Play copy never paints
// the button for a frame. An older app that does not say it is no Play copy.
import { nativeBridge } from '@erplora/ui/shell';
import { readonly, ref, type Ref } from 'vue';

/** The copy whose store forbids the way to the panel. */
const PLAY = 'play';

const IN_A_BROWSER: Readonly<Ref<boolean>> = readonly(ref(true));

/** The installed app's answer, shared by every screen's bar of this page; `undefined` until asked. */
let asked: { offered: Ref<boolean> } | undefined;

/** Whether this copy of the Hub offers «erplora.com» (live: `false` until the installed app answers). */
export function managementOffered(win: object = window): Readonly<Ref<boolean>> {
  const bridge = nativeBridge(win);
  if (!bridge) return IN_A_BROWSER;
  if (!asked) {
    const question = { offered: ref(false) };
    asked = question;
    bridge.invoke('device_context').then(
      (context) => {
        question.offered.value = (context as { distribution?: unknown } | null)?.distribution !== PLAY;
      },
      (error: unknown) => {
        // Not offered while it cannot be told; the next screen asks again.
        console.error('hub: device_context failed', error);
        if (asked === question) asked = undefined;
      },
    );
  }
  return readonly(asked.offered);
}

/** Forgets the installed app's answer (tests). */
export function forgetAppDistribution(): void {
  asked = undefined;
}
