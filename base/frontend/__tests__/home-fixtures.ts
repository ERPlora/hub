// What the Home reads, for the tests of the Home and of its pieces: a panel as `base.widget.catalog` answers it, and a
// step of the setup checklist and the checklist as `base.setup.status` does. One fixture each, so a field they gain is
// added once.
import type { SetupItem, SetupStatus, WidgetDef } from '../operations';

/** A KPI panel of the demo app, its app taken from `key`'s prefix and titled by it; `fields` change it. */
export function widget(key: string, fields: Partial<WidgetDef> = {}): WidgetDef {
  return {
    key,
    app: key.split('.')[0],
    title: key,
    icon: '',
    category: 'Demo',
    size: 'md',
    default: false,
    kind: 'kpi',
    operation: 'demo.item.stats',
    params: {},
    map: { value: 'open' },
    options: {},
    component: null,
    refresh_on: [],
    live: true,
    ...fields,
  };
}

/** A pending, functional step of the checklist that the person may do, its app taken from `key`'s prefix and titled by
 *  it; `fields` change it. */
export function setupItem(key: string, fields: Partial<SetupItem> = {}): SetupItem {
  return {
    key,
    app: key.split('.')[0],
    state: 'pending',
    level: 'functional',
    required: true,
    actionable: true,
    title: key,
    description: '',
    icon: 'ion:settings-outline',
    route: `/${key}`,
    order: 50,
    ...fields,
  };
}

/** The checklist of `items`, counted as the server counts it: pending, unavailable and pending legal ones. */
export function setupStatus(items: SetupItem[], fields: Partial<SetupStatus> = {}): SetupStatus {
  const pending = items.filter((i) => i.state === 'pending').length;
  const unavailable = items.filter((i) => i.state === 'unavailable').length;
  const blocking = items.filter((i) => i.state === 'pending' && i.level === 'legal').length;
  return { total: items.length, pending, unavailable, blocking_pending: blocking, items, ...fields };
}
