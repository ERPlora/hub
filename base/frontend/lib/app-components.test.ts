// The components an app gives base to mount where it says (a panel of the Home, BASE-G168; a card of System, hub#683):
// one of its own `apps/<app>/frontend/components/<name>.vue`, by its file name, loaded on demand; never a path.
import { describe, expect, it } from 'vitest';

import { appComponent } from './app-components';

describe('appComponent', () => {
  it('loads a component of an app by its file name', async () => {
    const loader = appComponent('demo', 'ItemStats');
    expect(loader).toBeTypeOf('function');
    expect((await loader!()).default).toBeTruthy();
  });

  it('has none for a name its app does not have, nor for another app’s', () => {
    expect(appComponent('demo', 'Nope')).toBeUndefined();
    expect(appComponent('printing', 'ItemStats')).toBeUndefined();
  });

  it('never follows a path', () => {
    expect(appComponent('demo', '../components/ItemStats')).toBeUndefined();
    expect(appComponent('demo/frontend/components', 'ItemStats')).toBeUndefined();
  });
});
