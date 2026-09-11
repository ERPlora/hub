// The assistant is the SECOND surface of `hub.setup.status` (hub#373) — the checklist card was the
// first (hub#372). Both read the SAME document, so what these tests protect is not the wording of a
// prompt: it is that what the assistant tells the user matches what the runtime answered.
//
//   - the briefing IS the document: every pending item travels with the title, the description, the
//     screen and the `actions` the query returned, in the query's order, and nothing else is added;
//   - an `unavailable` item is NEVER handed over as a task — not even its screen is named: it is our
//     breakdown, and «go install an app» against a catalogue that offers nothing sends the user to a
//     screen where they can do nothing;
//   - ⛔ is not a strong recommendation: it is the statement that the runtime REJECTS the operation.
//     Softening it promises a protection that does not exist; painting it on a 🟡 promises a gate
//     that will not fire;
//   - an absence is not an answer: a document that could not be read never becomes «you are all set».
import { describe, expect, it } from 'vitest';

import { parseSetupStatus, type SetupStatus } from './setup-status';
import { assistantTasks, setupBriefing } from './assistant-setup';

/** An item as the runtime emits it: every key present, `module_id` null for a core item. */
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

/** The document, with the counters the runtime computes over those items. */
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

/** The briefing for a document, in the language the shell is in. */
function brief(doc: SetupStatus | null, opts: Record<string, unknown> = {}): string {
  return setupBriefing(doc, { locale: 'es', ...opts });
}

/** What the briefing puts under «still to do» — the only part that is the user's to act on. */
function todoSection(text: string): string {
  const start = text.indexOf('STILL TO DO');
  const rest = text.slice(start);
  const end = rest.indexOf('\n\n');
  return end === -1 ? rest : rest.slice(0, end);
}

describe('the tasks the assistant may hand out', () => {
  it('only the pending ones: a `done` has nothing left and an `unavailable` cannot be finished', () => {
    const doc = status([
      item('apps', { state: 'unavailable' }),
      item('taxes.setup', { state: 'pending' }),
      item('team', { state: 'done' }),
    ]);

    expect(assistantTasks(doc).map((i) => i.key)).toEqual(['taxes.setup']);
  });

  it('in the order the query fixed, never re-sorted by this layer', () => {
    const doc = status([
      item('business_identity', { level: 'legal', order: 40 }),
      item('apps', { level: 'functional', order: 10 }),
    ]);

    expect(assistantTasks(doc).map((i) => i.key)).toEqual(['business_identity', 'apps']);
  });

  it('nothing at all while the query has not answered', () => {
    expect(assistantTasks(null)).toEqual([]);
  });
});

describe('the briefing is the document, not a list of its own', () => {
  it('every pending item travels with its title, its description and its screen', () => {
    const text = brief(status([item('team', { title: 'Your team', description: 'Add your people.', route: '/employees' })]));

    expect(text).toContain('Your team');
    expect(text).toContain('Add your people.');
    expect(text).toContain('/employees');
  });

  it('it carries the item’s `actions`: the ways in travel in the data so nobody guesses them', () => {
    const text = brief(status([item('apps', { actions: ['template', 'catalog'] })]));

    expect(text).toContain('template, catalog');
    // …and the vocabulary is spelled out, or a bare «catalog» is a word the model has to invent a
    // meaning for.
    expect(text).toContain('template = ');
    expect(text).toContain('catalog = ');
    expect(text).toContain('manual = ');
    expect(text).toContain('assistant = ');
  });

  it('a module item says which module it is, so a tool call can name it', () => {
    // Title and route on purpose say nothing about the module: the id has to travel on its own.
    const text = brief(status([item('verifactu.setup', { title: 'Set up invoicing', route: '/x' })]));

    expect(text).toContain('module: verifactu');
  });

  it('the items keep the query’s order', () => {
    const text = todoSection(
      brief(status([item('business_identity', { order: 40 }), item('team', { order: 80 })])),
    );

    expect(text.indexOf('Your business_identity')).toBeLessThan(text.indexOf('Your team'));
  });

  it('nothing is filtered again: a 🟡 the query returned is in the briefing too', () => {
    const text = todoSection(brief(status([item('team', { level: 'recommended' })])));

    expect(text).toContain('Your team');
  });

  it('it says the list is closed: no item may be invented on top of it', () => {
    expect(brief(status([item('team')]))).toContain('do not invent');
  });

  it('the counters are the query’s, never a recount of what fits in a prompt', () => {
    const text = brief(
      status([
        item('business_identity', { level: 'legal' }),
        item('team'),
        item('apps', { state: 'done' }),
      ]),
    );

    // 2 pending of 3, of which 1 is ⛔ — the split the runtime guarantees.
    expect(text).toContain('2 of 3');
    expect(text).toContain('blocking invoicing: 1');
  });

  it('it names the item the way the checklist names it: two surfaces, one name', () => {
    // A core item's `key` is also its i18n key (setup-status.md §6bis); the payload's English title
    // is the fallback. If the assistant used the fallback while the card shows the translation, the
    // user is told about an item they cannot find on screen.
    const text = brief(status([item('team', { title: 'Your team', description: 'Add your people.' })]), {
      translate: (key: string) =>
        ({
          'setup.items.team.title': 'Tu equipo',
          'setup.items.team.description': 'Añade a quien usará el TPV.',
        })[key] ?? null,
    });

    expect(text).toContain('Tu equipo');
    expect(text).toContain('Añade a quien usará el TPV.');
    expect(text).not.toContain('Your team');
    expect(text).not.toContain('Add your people.');
  });
});

describe('an `unavailable` item is never handed to the user', () => {
  const doc = status([
    item('apps', { state: 'unavailable', title: 'Your apps', route: '/apps' }),
    item('team', { state: 'pending', title: 'Your team', route: '/employees' }),
  ]);

  it('it is not a task: it does not appear among the things still to do', () => {
    expect(todoSection(brief(doc))).not.toContain('Your apps');
  });

  it('its screen is never named: sending them there is sending them nowhere', () => {
    expect(brief(doc)).not.toContain('/apps');
  });

  it('but it is said out loud, and said as ours', () => {
    const text = brief(doc);

    expect(text).toContain('ON US');
    expect(text).toContain('Your apps');
  });

  it('and the pending one beside it is still offered', () => {
    expect(todoSection(brief(doc))).toContain('Your team');
  });
});

describe('a wall that is not the user’s to bring down (hub#435)', () => {
  const doc = status([
    item('business_identity', {
      level: 'legal',
      actionable: false,
      title: 'Your business details',
      route: '/settings',
    }),
    item('team', { title: 'Your team', route: '/employees' }),
  ]);

  it('is never handed over as a task: they would be refused on the other side', () => {
    expect(assistantTasks(doc).map((i) => i.key)).toEqual(['team']);
    expect(todoSection(brief(doc))).not.toContain('Your business details');
  });

  it('its screen is not named: sending them there is sending them into a refusal', () => {
    expect(brief(doc)).not.toContain('/settings');
  });

  it('but it IS said, and said as a block: silence would leave the refusal unexplained', () => {
    const text = brief(doc);

    expect(text).toContain('Your business details');
    expect(text).toContain('BLOCKS INVOICING');
  });

  it('and it says who can do it, so the answer is not a dead end', () => {
    expect(brief(doc)).toContain('administrator');
  });

  it('it is not «on us»: nothing of ours is broken, somebody else just has to type it', () => {
    const text = brief(doc);
    const onUs = text.slice(text.indexOf('ON US'));

    expect(text.includes('ON US') && onUs.includes('Your business details')).toBe(false);
  });

  it('the counter matches the lines that follow it: 1 task, not 2', () => {
    // The delegated item is still `pending` for the runtime, so `status.pending` is 2. Printing that
    // above a single line would have the model announce a task it cannot name.
    const text = brief(doc);

    expect(text).toContain('1 of 2');
    // …and the wall is still counted where it is counted: the ⛔ figure is the query's.
    expect(text).toContain('blocking invoicing: 1');
  });

  it('with nothing left BUT the delegated wall, the hub is not called finished', () => {
    const onlyWall = status([
      item('business_identity', { level: 'legal', actionable: false, title: 'Your business details' }),
    ]);
    const text = brief(onlyWall);

    expect(text).not.toContain('every item of the checklist is done');
    expect(text).toContain('Your business details');
  });
});

describe('⛔ is a rejection of the runtime, not a strong recommendation', () => {
  const legal = status([item('business_identity', { level: 'legal' })]);
  const recommended = status([item('team', { level: 'recommended' })]);
  const functional = status([item('taxes.setup', { level: 'functional' })]);

  it('a ⛔ item says the hub REJECTS the operation', () => {
    const text = brief(legal);

    expect(text).toContain('BLOCKS INVOICING');
    expect(text).toContain('rejects');
  });

  it('it is explicitly not advice: a softened ⛔ promises a protection that does not exist', () => {
    expect(brief(legal)).toContain('not advice');
  });

  it('a 🟡 never says it: a false ⛔ promises a gate that will not fire', () => {
    const text = brief(recommended);

    expect(text).not.toContain('BLOCKS INVOICING');
    expect(text).toContain('recommended');
  });

  it('a 🔴 is its own thing: it matters, but nothing rejects it', () => {
    const text = brief(functional);

    expect(text).not.toContain('BLOCKS INVOICING');
    expect(text).toContain('important');
    // …and it does NOT borrow ⛔'s sentence from the other side (hub#1726): «needed to sell» named a
    // gate the core forbids a manifest from having. The wording itself is held in
    // `i18n/setup-level-copy.test.ts`, next to the badge that has to agree with it.
    expect(text).not.toMatch(/\bsell\b/i);
  });

  it('the level is READ, never re-derived from `required`', () => {
    // `required` cannot express ⛔ (setup-status.md §4): a surface deriving the level from it would
    // paint a ⛔ on every 🔴.
    const text = brief(status([item('taxes.setup', { level: 'functional', required: true })]));

    expect(text).not.toContain('BLOCKS INVOICING');
  });

  it('a ⛔ already done is not announced as a block: the level is orthogonal to the state', () => {
    const text = brief(status([item('business_identity', { level: 'legal', state: 'done' })]));

    expect(text).not.toContain('BLOCKS INVOICING');
  });
});

describe('what the briefing must never claim', () => {
  it('a document it could not read is not «all set»', () => {
    const text = brief(null);

    expect(text).toContain('could NOT be read');
    expect(text).not.toContain('STILL TO DO');
  });

  it('an empty answer is silence, not a finished hub', () => {
    // Same rule as the card: celebrating an empty document is the false «done» that buries the task.
    const text = brief(status([]));

    expect(text).toContain('could NOT be read');
  });

  it('a finished hub does say so', () => {
    const text = brief(status([item('team', { state: 'done' })]));

    expect(text).toContain('nothing');
    expect(text).not.toContain('could NOT be read');
  });

  it('with nothing pending but something broken, it does not call the hub finished', () => {
    const text = brief(status([item('apps', { state: 'unavailable' })]));

    expect(text).not.toContain('every item of the checklist is done');
    expect(text).toContain('ON US');
  });

  it('a done item is listed as done, and never as a task', () => {
    const text = brief(status([item('team', { state: 'done' }), item('apps', { state: 'pending' })]));

    expect(text).toContain('ALREADY DONE');
    expect(todoSection(text)).not.toContain('Your team');
  });
});

describe('it opens on the item the user asked about — never a blank chat', () => {
  const doc = status([
    item('business_identity', { level: 'legal', title: 'Your business details' }),
    item('team', { level: 'recommended', title: 'Your team' }),
  ]);

  it('the focused item is named before the list', () => {
    const text = brief(doc, { focusKey: 'team' });

    expect(text).toContain('ASKING ABOUT');
    expect(text.indexOf('ASKING ABOUT')).toBeLessThan(text.indexOf('STILL TO DO'));
    expect(text.slice(0, text.indexOf('STILL TO DO'))).toContain('Your team');
  });

  it('the rest of the checklist is still there: a focus is not a filter', () => {
    expect(todoSection(brief(doc, { focusKey: 'team' }))).toContain('Your business details');
  });

  it('a key the document does not have leaves the general briefing standing', () => {
    const text = brief(doc, { focusKey: 'nope' });

    expect(text).not.toContain('ASKING ABOUT');
    expect(text).toContain('STILL TO DO');
  });

  it('focusing an `unavailable` does not turn it into a task', () => {
    const broken = status([item('apps', { state: 'unavailable', title: 'Your apps', route: '/apps' })]);
    const text = brief(broken, { focusKey: 'apps' });

    expect(text).toContain('ASKING ABOUT');
    expect(text).toContain('ON US');
    // The opening does not read like a task either: no «how to finish it», and no screen — the
    // state IS the statement that the screen does not help.
    expect(text).not.toContain('how to finish it');
    expect(text).not.toContain('/apps');
  });

  it('without a focus it still opens loaded: the whole checklist is the context', () => {
    const text = brief(doc);

    expect(text).not.toContain('ASKING ABOUT');
    expect(todoSection(text)).toContain('Your business details');
  });
});

describe('the answer belongs to the user, the briefing to us', () => {
  it('the briefing tells the model which language to answer in', () => {
    expect(brief(status([item('team')]), { locale: 'es' })).toContain('locale: es');
    expect(brief(status([item('team')]), { locale: 'en' })).toContain('locale: en');
  });

  it('and it says so even when there is no document to describe', () => {
    expect(brief(null, { locale: 'es' })).toContain('locale: es');
  });
});
