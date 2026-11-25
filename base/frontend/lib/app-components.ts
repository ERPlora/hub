// The components an app gives base to mount where it says: a panel of the Home with a `component` of its own and a
// card of System › «Usage and plan»; and the one an app mounts from another that its `requires` do not let it import,
// found by name as that app's operations are. Each is one of `apps/<app>/frontend/components/<name>.vue`, named by its file, and
// loads on demand in its own chunk; a name its app does not have gives none (a path never names one: the glob's keys
// are the files themselves), and whoever asked says so.
import { type Component, defineAsyncComponent } from 'vue';

export type ComponentLoader = () => Promise<{ default: Component }>;

/** Every app's components, loaded on demand. */
const COMPONENTS = import.meta.glob<{ default: Component }>('../../../apps/*/frontend/components/*.vue');

export function appComponent(app: string, name: string): ComponentLoader | undefined {
  return COMPONENTS[`../../../apps/${app}/frontend/components/${name}.vue`];
}

/** What `loader` brings, as a component that loads once it renders; none without a loader (its app has no such
 *  component). When the code does not arrive, `failed` hears why and it renders nothing. */
export function loadedComponent(loader: ComponentLoader | undefined, failed: (error: unknown) => void): Component | null {
  if (!loader) return null;
  return defineAsyncComponent({
    loader: () => loader().then((module) => module.default),
    onError(error, _retry, fail) {
      failed(error);
      fail();
    },
  });
}
