// The checklist reads `hub.setup.status` — ONE query, no loop in the browser (hub#372).
//
// What these tests protect is the honesty of the reading, not the layout:
//   - one request to the runtime, and the manifests are never walked again from here;
//   - the counters are the QUERY's counters (a surface that re-aggregates them diverges);
//   - `unavailable` is neither a pending nor a done: it is not the user's to do, so it is never
//     offered as an action;
//   - what the query omitted stays omitted — the widget never invents an item nor re-filters one.
import { describe, expect, it, vi, beforeEach } from 'vitest';

const loadInstalledManifests = vi.fn();
vi.mock('./module-loader', () => ({
  loadInstalledManifests: (...a: unknown[]) => loadInstalledManifests(...a),
}));

import {
  MAX_VISIBLE_ROWS,
  SETUP_STATUS_QUERY,
  checklistView,
  isActionable,
  parseSetupStatus,
  refreshSetupStatus,
  setupStatus,
  type SetupItem,
} from './setup-status';

type ItemOverrides = Partial<Record<keyof SetupItem, unknown>>;

/** An item as the runtime emits it: every key present, `module_id` null for a core item. */
function item(key: string, over: ItemOverrides = {}): Record<string, unknown> {
  return {
    key,
    source: key.includes('.') ? 'module' : 'core',
    module_id: key.includes('.') ? key.split('.')[0] : null,
    state: 'pending',
    required: true,
    level: 'functional',
    title: `Your ${key}`,
    description: `Set up ${key}.`,
    icon: 'settings-outline',
    route: `/${key}`,
    order: 10,
    actions: ['manual'],
    ...over,
  };
}

/** The document, with the counters the runtime computes over those items. */
function doc(items: Record<string, unknown>[], over: Record<string, unknown> = {}) {
  const count = (state: string) => items.filter((i) => i.state === state).length;
  return {
    items,
    total: items.length,
    pending: count('pending'),
    unavailable: count('unavailable'),
    blocking_pending: items.filter((i) => i.state === 'pending' && i.level === 'legal').length,
    ...over,
  };
}

function clientReturning(payload: unknown) {
  return { query: vi.fn().mockResolvedValue(payload) } as unknown as Parameters<typeof refreshSetupStatus>[0] & {
    query: ReturnType<typeof vi.fn>;
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the read: ONE query, not a loop in the browser', () => {
  it('asks `hub.setup.status` once and does NOT walk the installed manifests', async () => {
    const client = clientReturning([doc([item('apps')])]);

    await refreshSetupStatus(client);

    expect(client.query).toHaveBeenCalledTimes(1);
    expect(client.query).toHaveBeenCalledWith(SETUP_STATUS_QUERY);
    expect(SETUP_STATUS_QUERY).toBe('hub.setup.status');
    // The ADR-0063 loop lived here: it collected the manifests and fired N queries. If it comes
    // back, the widget and the assistant diverge again — exactly what hub#369 closed.
    expect(loadInstalledManifests).not.toHaveBeenCalled();
  });

  it('unwraps the single row the document travels in', async () => {
    const client = clientReturning([doc([item('apps'), item('team', { state: 'done' })])]);

    await refreshSetupStatus(client);

    expect(setupStatus.value?.items.map((i) => i.key)).toEqual(['apps', 'team']);
    expect(setupStatus.value?.total).toBe(2);
  });

  it('a failing query does NOT wipe the last thing we knew, and does not blow up', async () => {
    await refreshSetupStatus(clientReturning([doc([item('apps')])]));
    const before = setupStatus.value;

    const broken = { query: vi.fn().mockRejectedValue(new Error('boot')) } as unknown as Parameters<
      typeof refreshSetupStatus
    >[0];
    await expect(refreshSetupStatus(broken)).resolves.toBeUndefined();

    expect(setupStatus.value).toBe(before);
  });

  it('a 200 that is NOT the document does not wipe what we knew either', async () => {
    // An error body with a 200, a proxy returning HTML: that is not an answer, and treating it as
    // one would empty the card of a hub that does have pending items.
    await refreshSetupStatus(clientReturning([doc([item('apps')])]));
    const before = setupStatus.value;

    await refreshSetupStatus(clientReturning({ detail: 'Not found' }));

    expect(setupStatus.value).toBe(before);
    expect(setupStatus.value?.items).toHaveLength(1);
  });

  it('a payload that is not the document is never taken for one', () => {
    for (const notADoc of [null, undefined, 7, 'nope', [], {}, [{ detail: 'denied' }]]) {
      expect(parseSetupStatus(notADoc), `${JSON.stringify(notADoc)} is not the document`).toBeNull();
    }
  });
});

describe('the counters are the QUERY\'s, not a count of what was painted', () => {
  it('«done» comes from total − pending − unavailable, not from the rows on screen', () => {
    const items = [
      item('apps', { state: 'unavailable' }),
      item('taxes.setup', { state: 'pending' }),
      item('inventory.setup', { state: 'done' }),
      item('business_identity', { state: 'done', level: 'legal' }),
    ];
    const view = checklistView(parseSetupStatus([doc(items)]));

    expect(view.total).toBe(4);
    expect(view.pending).toBe(1);
    expect(view.unavailable).toBe(1);
    expect(view.done).toBe(2);
    // Fewer rows are painted than the total: the counter is still the whole hub's.
    expect(view.rows.length).toBeLessThan(view.total);
  });

  it('an `unavailable` is NOT counted as done: with two counters it would be a faked success', () => {
    const view = checklistView(parseSetupStatus([doc([item('apps', { state: 'unavailable' })])]));

    expect(view.unavailable).toBe(1);
    expect(view.done).toBe(0);
    expect(view.complete).toBe(false);
  });

  it('`blocking_pending` travels as-is: it is the only thing the strip will read', () => {
    const view = checklistView(
      parseSetupStatus([doc([item('business_identity', { level: 'legal' }), item('apps')])]),
    );

    expect(view.blockingPending).toBe(1);
  });
});

describe('what is in sight and what is folded', () => {
  it('pending ⛔ and 🔴 are in sight; 🟡 folds behind «view all»', () => {
    const items = [
      item('business_identity', { level: 'legal' }),
      item('taxes.setup', { level: 'functional' }),
      item('printing.setup', { level: 'recommended' }),
    ];
    const status = parseSetupStatus([doc(items)]);

    const folded = checklistView(status);
    expect(folded.rows.map((r) => r.key)).toEqual(['business_identity', 'taxes.setup']);
    expect(folded.hidden).toBe(1);

    const open = checklistView(status, { expanded: true });
    expect(open.rows.map((r) => r.key)).toEqual(['business_identity', 'taxes.setup', 'printing.setup']);
    expect(open.hidden).toBe(0);
  });

  it('the practice of the trade: never more than 5 rows in sight', () => {
    const items = Array.from({ length: 9 }, (_, n) => item(`m${n}.setup`));
    const status = parseSetupStatus([doc(items)]);

    expect(checklistView(status).rows).toHaveLength(MAX_VISIBLE_ROWS);
    expect(MAX_VISIBLE_ROWS).toBe(5);
    expect(checklistView(status, { expanded: true }).rows).toHaveLength(9);
  });

  it('if only 🟡 are left, they show: a card with an empty body says nothing', () => {
    const items = [
      item('apps', { state: 'done' }),
      item('team', { level: 'recommended', state: 'pending' }),
    ];
    const view = checklistView(parseSetupStatus([doc(items)]));

    expect(view.rows.map((r) => r.key)).toEqual(['team']);
    expect(view.complete).toBe(false);
  });

  it('what is done does not take up the short view, but is still there behind «view all»', () => {
    const items = [item('apps', { state: 'done' }), item('team')];
    const status = parseSetupStatus([doc(items)]);

    expect(checklistView(status).rows.map((r) => r.key)).toEqual(['team']);
    expect(checklistView(status, { expanded: true }).rows.map((r) => r.key)).toEqual(['apps', 'team']);
  });

  it('keeps the query ORDER: re-sorting here is the divergence hub#369 closed', () => {
    const items = [
      item('apps', { order: 10 }),
      item('business_identity', { order: 40, level: 'legal' }),
      item('verifactu.setup', { order: 60, level: 'legal' }),
    ];
    const view = checklistView(parseSetupStatus([doc(items)]), { expanded: true });

    expect(view.rows.map((r) => r.key)).toEqual(['apps', 'business_identity', 'verifactu.setup']);
  });
});

describe('the finished hub and the hub that says nothing', () => {
  it('with nothing pending and nothing broken, the checklist is FINISHED', () => {
    const items = [item('apps', { state: 'done' }), item('team', { state: 'done' })];
    const view = checklistView(parseSetupStatus([doc(items)]));

    expect(view.complete).toBe(true);
    expect(view.empty).toBe(false);
    expect(view.done).toBe(2);
    expect(view.rows).toEqual([]);
  });

  it('an EMPTY list neither blows up nor is celebrated as if everything were done', () => {
    const view = checklistView(parseSetupStatus([doc([])]));

    expect(view.empty).toBe(true);
    expect(view.complete).toBe(false);
    expect(view.rows).toEqual([]);
    expect(view.total).toBe(0);
  });

  it('with no document (early boot, denied query) there is nothing to paint', () => {
    const view = checklistView(null);

    expect(view.empty).toBe(true);
    expect(view.complete).toBe(false);
    expect(view.rows).toEqual([]);
  });
});

describe('what the query omitted stays omitted', () => {
  it('invents no items: only what came in the answer is painted', () => {
    // An empty hub: the runtime omits what it could not evaluate and filters by country/permission.
    // The checklist does NOT filter again nor fill gaps — if it did, it would stop being the same
    // list the assistant reads.
    const view = checklistView(parseSetupStatus([doc([item('apps')])]), { expanded: true });

    expect(view.rows.map((r) => r.key)).toEqual(['apps']);
    expect(view.total).toBe(1);
  });

  it('an item whose `countries` do not apply never arrives: it is not rebuilt from the manifest', () => {
    const status = parseSetupStatus([doc([item('apps'), item('team', { level: 'recommended' })])]);

    expect(checklistView(status, { expanded: true }).rows.some((r) => r.key === 'verifactu.setup')).toBe(false);
  });
});

describe('`unavailable`: neither a pending to attempt nor a done', () => {
  it('offers no action — that screen would hand them a job they cannot finish', () => {
    const broken = parseSetupStatus([doc([item('apps', { state: 'unavailable' })])])!.items[0];

    expect(isActionable(broken)).toBe(false);
  });

  it('a pending one DOES offer an action, and a done one does not', () => {
    const status = parseSetupStatus([
      doc([item('apps'), item('team', { state: 'done' })]),
    ])!;

    expect(isActionable(status.items[0])).toBe(true);
    expect(isActionable(status.items[1])).toBe(false);
  });

  it('it shows in the list: hiding the only item an empty hub has is the false «done»', () => {
    const view = checklistView(parseSetupStatus([doc([item('apps', { state: 'unavailable' })])]));

    expect(view.rows.map((r) => r.key)).toEqual(['apps']);
  });

  it('keeps its `actions`: the signal that they do not work NOW is the state, and it is one', () => {
    const broken = parseSetupStatus([
      doc([item('apps', { state: 'unavailable', actions: ['template', 'catalog'] })]),
    ])!.items[0];

    expect(broken.actions).toEqual(['template', 'catalog']);
    expect(isActionable(broken)).toBe(false);
  });

  it('a state this shell does not know is never offered as a task', () => {
    // A future fourth state must not turn into a CTA on a guess.
    const future = parseSetupStatus([doc([item('apps', { state: 'quarantined' })])])!.items[0];

    expect(isActionable(future)).toBe(false);
  });
});

describe('what is handed to the assistant', () => {
  it('the pending ones, and NEVER an `unavailable`: there is no way to complete it', async () => {
    await refreshSetupStatus(
      clientReturning([
        doc([
          item('apps', { state: 'unavailable' }),
          item('taxes.setup', { state: 'pending' }),
          item('team', { state: 'done' }),
        ]),
      ]),
    );

    const { pendingSetups } = await import('./setup-status');
    expect(pendingSetups.value.map((s) => s.moduleId)).toEqual(['taxes']);
  });
});

describe('decision 1: the panel does not repeat what the apps card already offers', () => {
  it('with the apps card in sight, the checklist starts at item 2', () => {
    const items = [item('apps'), item('business_identity', { level: 'legal' })];
    const view = checklistView(parseSetupStatus([doc(items)]), { alreadyOnScreen: ['apps'] });

    expect(view.rows.map((r) => r.key)).toEqual(['business_identity']);
  });

  it('but an `unavailable` is NOT deduplicated: no other card says this one is broken', () => {
    const items = [item('apps', { state: 'unavailable' }), item('business_identity', { level: 'legal' })];
    const view = checklistView(parseSetupStatus([doc(items)]), { alreadyOnScreen: ['apps'] });

    expect(view.rows.map((r) => r.key)).toEqual(['apps', 'business_identity']);
  });

  it('the counter does NOT change when deduplicating: the item is still the hub\'s', () => {
    const items = [item('apps'), item('business_identity', { level: 'legal' })];
    const view = checklistView(parseSetupStatus([doc(items)]), { alreadyOnScreen: ['apps'] });

    expect(view.total).toBe(2);
    expect(view.pending).toBe(2);
  });
});
