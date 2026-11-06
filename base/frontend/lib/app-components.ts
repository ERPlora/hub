// The components an app gives base to mount where it says: a panel of the Home with a `component` of its own
// (BASE-G168) and a card of System › «Usage and plan» (hub#683). Each is one of `apps/<app>/frontend/components/
// <name>.vue`, named by its file, and loads on demand in its own chunk; a name that is a path, or one its app does not
// have, gives none, and whoever asked says so.
import type { Component } from 'vue';

export type ComponentLoader = () => Promise<{ default: Component }>;

/** Every app's components, loaded on demand. */
const COMPONENTS = import.meta.glob<{ default: Component }>('../../../apps/*/frontend/components/*.vue');
/** An app's label or a component's file name: never a path. */
const NAME = /^[A-Za-z]\w*$/;

export function appComponent(app: string, name: string): ComponentLoader | undefined {
  if (!NAME.test(app) || !NAME.test(name)) return undefined;
  return COMPONENTS[`../../../apps/${app}/frontend/components/${name}.vue`];
}
