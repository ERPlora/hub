// The pass to erplora.com (BASE-F11; ACCOUNTS-F29 of the SaaS): «Upgrade plan» and «Manage on erplora.com» arrive
// already signed in. `base.saas_pass.create` signs it at the click, never in the page: it lasts a minute and any script
// could read it. This is the Hub's second door out, after `openExternalLink`: a browser blocks a window opened after an
// `await`, so the blank tab opens in the click and gets its address when the pass comes. The installed app has no tabs:
// the address goes to the device's browser by `openExternalLink`. Whatever goes wrong the usual address opens, which
// still works, asking to sign in: a button that does nothing is the defect this must never bring back.
import { type LiveClient, useCommand } from '@erplora/ui/sdk';
import { nativeBridge, openExternalLink } from '@erplora/ui/shell';

export type SaasPassNext = 'plan' | 'business';

/** How long a person looks at a blank tab before it gets the usual address: the request itself has no time limit. */
export const SIGN_TIMEOUT_MS = 8000;

/** `client`: for a click outside any component's setup (the assistant's panel hands its own); the page's otherwise. */
export function useSaasPass(client?: LiveClient): { openSaasPass: (next: SaasPassNext, usual: string, event: Event) => void } {
  const { run } = useCommand('base.saas_pass.create', { client });

  /** The address to open: the signed one, or the usual one when it fails or takes too long. */
  function addressOf(next: SaasPassNext, usual: string): Promise<string> {
    return new Promise((resolve) => {
      const giveUp = setTimeout(() => resolve(usual), SIGN_TIMEOUT_MS);
      run({ next })
        .then(
          ({ url }) => resolve(url),
          (error: unknown) => {
            console.error('hub: base.saas_pass.create failed', error);
            resolve(usual);
          },
        )
        .finally(() => clearTimeout(giveUp));
    });
  }

  function openSaasPass(next: SaasPassNext, usual: string, event: Event): void {
    if (nativeBridge(window)) {
      event.preventDefault();
      void addressOf(next, usual).then((address) => openExternalLink(address, event));
      return;
    }
    // Not `noopener` in its features: `window.open` would then give back no tab to send to the address.
    const tab = window.open('about:blank', '_blank');
    // Blocked: the click goes on, and the link itself opens the usual address.
    if (tab === null) return;
    event.preventDefault();
    tab.opener = null;
    void addressOf(next, usual).then((address) => {
      tab.location.href = address;
    });
  }

  return { openSaasPass };
}
