// The shape of the blocking strip (hub#374) — the third surface of `hub.setup.status`.
//
// What these tests protect is the claim the strip makes: **the runtime is going to reject the
// operation**. ⛔ is not a stronger 🔴, it is the statement that `enforce_fiscal_precondition`
// (ADR-0203) says no. So:
//   - it shows up for `blocking_pending > 0` and for nothing else — a 🔴 or a 🟡 must never raise it,
//     or the strip becomes furniture nobody reads;
//   - it names what is missing and carries its `route`, because a strip that cannot be dismissed and
//     does not say what to do is a dead end;
//   - it counts with the query's counter, never with a recount of the rows it painted;
//   - a failed read leaves it silent instead of inventing an alarm.
import { describe, expect, it } from 'vitest';

import {
  MAX_VISIBLE_ROWS,
  blockingView,
  checklistView,
  isBlocking,
  parseSetupStatus,
  type SetupStatus,
} from './setup-status';

/** One item as `hub.setup.status` emits it. */
function item(key: string, over: Record<string, unknown> = {}): Record<string, unknown> {
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

/** The document, with the counters the runtime would have computed for these items. */
function status(items: Record<string, unknown>[], over: Record<string, unknown> = {}): SetupStatus | null {
  const count = (state: string) => items.filter((i) => i.state === state).length;
  return parseSetupStatus([
    {
      items,
      total: items.length,
      pending: count('pending'),
      unavailable: count('unavailable'),
      blocking_pending: items.filter((i) => i.state === 'pending' && i.level === 'legal').length,
      ...over,
    },
  ]);
}

describe('the strip appears only for what the runtime rejects', () => {
  it('shows up when something is ⛔ and still pending', () => {
    const view = blockingView(status([item('business_identity', { level: 'legal' })]));

    expect(view.visible).toBe(true);
    expect(view.count).toBe(1);
  });

  it('stays down when nothing blocks, however much is pending', () => {
    // Two items the user still owes and one that is nice to have. None of them is a gate: the till
    // sells, the hub invoices. A strip here would be noise on every screen of the product.
    const view = blockingView(
      status([
        item('apps', { level: 'functional' }),
        item('taxes.setup', { level: 'functional' }),
        item('team', { level: 'recommended' }),
      ]),
    );

    expect(view.visible).toBe(false);
    expect(view.count).toBe(0);
  });

  it('stays down once the ⛔ item is done, without waiting for the rest of the list', () => {
    const view = blockingView(
      status([item('business_identity', { level: 'legal', state: 'done' }), item('team', { level: 'recommended' })]),
    );

    expect(view.visible).toBe(false);
  });

  it('never rises for an `unavailable`: that one is our breakdown, not a gate', () => {
    // `apps` is the only item that reaches the third state and it is 🔴, so a hub that cannot install
    // anything still invoices. Raising the strip there would blame the user for a hole of ours.
    const view = blockingView(status([item('apps', { level: 'functional', state: 'unavailable' })]));

    expect(view.visible).toBe(false);
    expect(view.items).toEqual([]);
  });
});

describe('it says WHAT is missing and where to fix it', () => {
  it('names the ⛔ pending items, in the order the query gave them', () => {
    const view = blockingView(
      status([
        item('business_identity', { level: 'legal', order: 40 }),
        item('invoice_series.setup', { level: 'functional', order: 50 }),
        item('verifactu.setup', { level: 'legal', order: 60 }),
      ]),
    );

    expect(view.items.map((i) => i.key)).toEqual(['business_identity', 'verifactu.setup']);
  });

  it('every named item carries the screen that fixes it', () => {
    const view = blockingView(
      status([item('business_identity', { level: 'legal', route: '/settings' })]),
    );

    expect(view.items[0]?.route).toBe('/settings');
  });

  it('does not name a ⛔ that is already done', () => {
    const view = blockingView(
      status([
        item('business_identity', { level: 'legal', state: 'done' }),
        item('verifactu.setup', { level: 'legal' }),
      ]),
    );

    expect(view.items.map((i) => i.key)).toEqual(['verifactu.setup']);
  });

  it('keeps quiet when the counter claims a gate it cannot name', () => {
    // The runtime derives the counter from the same (already filtered) list, so the two agree by
    // construction — this is a payload that contradicts itself. A strip that shouts «you cannot
    // invoice» with nothing to name and nowhere to go is worse than silence: it cannot be dismissed
    // and it cannot be acted on.
    const view = blockingView(status([item('team', { level: 'recommended' })], { blocking_pending: 3 }));

    expect(view.visible).toBe(false);
    expect(view.items).toEqual([]);
  });
});

describe('the counter belongs to the query', () => {
  it('keeps quiet when the counter says no gate, whatever the rows look like', () => {
    // The counter is the runtime's verdict on its own gate; the rows are only what the strip can
    // name. Re-deciding here from the rows is the second source of truth this subsystem closed —
    // and it is the direction that matters most, because it would put a red band over the whole
    // product on a hub that invoices perfectly.
    const view = blockingView(status([item('business_identity', { level: 'legal' })], { blocking_pending: 0 }));

    expect(view.visible).toBe(false);
    expect(view.count).toBe(0);
  });

  it('reports what the runtime counted, not what the strip listed', () => {
    // A document the runtime would never emit, on purpose: if the strip re-aggregated the rows it
    // would answer 1 and quietly disagree with the panel and with the assistant.
    const view = blockingView(status([item('business_identity', { level: 'legal' })], { blocking_pending: 2 }));

    expect(view.count).toBe(2);
    expect(view.items).toHaveLength(1);
  });
});

describe('a broken read is silence, never an alarm', () => {
  it('survives a document that never arrived', () => {
    const view = blockingView(null);

    expect(view.visible).toBe(false);
    expect(view.items).toEqual([]);
    expect(view.count).toBe(0);
  });

  it('survives a payload that is not the document', () => {
    expect(blockingView(parseSetupStatus({ error: 'boom' })).visible).toBe(false);
  });

  it('survives a document whose items are missing every field', () => {
    const view = blockingView(parseSetupStatus([{ items: [{}], blocking_pending: 1 }]));

    expect(view.visible).toBe(false);
  });
});

describe('⛔ AND pending: the two axes, never fused', () => {
  it.each([
    ['legal', 'pending', true],
    ['legal', 'done', false],
    ['legal', 'unavailable', false],
    ['functional', 'pending', false],
    ['recommended', 'pending', false],
  ])('level %s + state %s → blocking: %s', (level, state, expected) => {
    const parsed = status([item('x', { level, state })]);

    expect(isBlocking(parsed!.items[0]!)).toBe(expected);
  });
});

describe('not twice on the same screen', () => {
  const blocked = () =>
    status([item('business_identity', { level: 'legal' }), item('verifactu.setup', { level: 'legal' })]);

  it('yields on a screen that already carries the whole checklist', () => {
    // The panel's card says strictly more about the same items —name, description, level pill and
    // the same way in— a screenful below. Spending chrome on a second red call to action there is
    // the duplication decision 1 of the plan already ruled out.
    const view = blockingView(blocked(), { checklistOnScreen: true });

    expect(view.visible).toBe(false);
  });

  it('yielding is not forgetting: the items and the counter stand', () => {
    const view = blockingView(blocked(), { checklistOnScreen: true });

    expect(view.count).toBe(2);
    expect(view.items).toHaveLength(2);
  });

  it('is up everywhere else — the till never opens the panel', () => {
    expect(blockingView(blocked(), { checklistOnScreen: false }).visible).toBe(true);
    expect(blockingView(blocked()).visible).toBe(true);
  });

  it('the card it yields to never folds a ⛔ away on that screen', () => {
    // What makes yielding safe. The card shows `MAX_VISIBLE_ROWS` rows and the ⛔ ones are never the
    // folded kind (only 🟡 are), but the full list is ten items and a ⛔ could still be pushed past
    // the cut. On the panel it cannot: `apps` is deduplicated there, which buys back the slot.
    const everything = [
      item('apps', { order: 10 }),
      item('taxes.setup', { order: 20 }),
      item('inventory.setup', { order: 30 }),
      item('business_identity', { level: 'legal', order: 40 }),
      item('invoice_series.setup', { order: 50 }),
      item('verifactu.setup', { level: 'legal', order: 60 }),
      item('printing.setup', { level: 'recommended', order: 70 }),
      item('team', { level: 'recommended', order: 80 }),
      item('cash_register.setup', { level: 'recommended', order: 90 }),
      item('tables.setup', { level: 'recommended', order: 100 }),
    ];
    const doc = status(everything);
    const panel = checklistView(doc, { alreadyOnScreen: ['apps'] });

    expect(panel.rows).toHaveLength(MAX_VISIBLE_ROWS);
    const painted = panel.rows.map((r) => r.key);
    for (const missing of blockingView(doc).items) {
      expect(painted, `${missing.key} would be folded away with the strip down`).toContain(missing.key);
    }
  });
});
