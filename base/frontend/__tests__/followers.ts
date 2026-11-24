// The followers beside the pane (`BackgroundChrome`: AppsFollower, AccessFollower, LanguageFollower) mounted as base
// mounts them: on a session the test changes while the screen is open, with a screen at each of `screens`
// (`/<app>/<page>`, carrying its app as the apps' own routes do, so the app gate judges it) and the live call they open.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component, Ref } from 'vue';

import { mountBase } from './mount-base';

export interface FollowerOptions {
  session: Ref<SessionMe>;
  path: string;
  screens: string[];
  /** Other paths the router knows, outside any app. */
  routes?: string[];
}

export async function openFollower(follower: Component, { session, path, screens, routes = [] }: FollowerOptions) {
  const m = await mountBase(follower, { path, routes, session });
  for (const screen of screens) {
    const app = screen.split('/')[1];
    m.router.addRoute({ path: screen, component: { template: '<div />' }, meta: { auth: true, app } });
  }
  await m.router.replace(path);
  const call = await m.live();
  return { ...m, call };
}
