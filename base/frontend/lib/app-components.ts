// The components an app gives base to mount where it says: a panel of the Home with a `component` of its own
// (BASE-G168) and a card of System › «Usage and plan» (hub#683). Each is one of `apps/<app>/frontend/components/
// <name>.vue`, named by its file, and loads on demand in its own chunk; a name its app does not have gives none (a
// path never names one: the glob's keys are the files themselves), and whoever asked says so.
import type { Component } from 'vue';

export type ComponentLoader = () => Promise<{ default: Component }>;

/** Every app's components, loaded on demand. */
const COMPONENTS = import.meta.glob<{ default: Component }>('../../../apps/*/frontend/components/*.vue');

export function appComponent(app: string, name: string): ComponentLoader | undefined {
  return COMPONENTS[`../../../apps/${app}/frontend/components/${name}.vue`];
}
