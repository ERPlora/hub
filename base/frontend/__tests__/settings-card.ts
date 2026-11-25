// Test helper of the cards of Settings that follow one live setting: the card mounted on /settings with its live
// call, its switch, and what it posted.
import { type Component } from 'vue';

import { mountBase, type MountOptions } from './mount-base';

export async function openSettingsCard(component: Component, options: MountOptions = {}) {
  const m = await mountBase(component, { path: '/settings', routes: ['/settings'], ...options });
  const call = await m.live();
  return { ...m, call };
}

export const switchOf = (m: { wrapper: { get: (s: string) => { element: Element } } }, testid: string) =>
  m.wrapper.get(`[data-testid="${testid}"]`).element as HTMLElement & { checked: boolean; disabled: boolean };

/** What the page posted: [path, body]. */
export function posted(m: { net: { api: { url: string; init: RequestInit }[] } }) {
  return m.net.api.map((call) => [new URL(call.url, 'http://a.localhost').pathname, JSON.parse(String(call.init.body))]);
}
