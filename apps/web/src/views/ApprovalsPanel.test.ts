// @vitest-environment happy-dom
// hub#512 — the screen that finally reads the PIN approval record (People › Approvals).
// hub#884 — and reads it in PAGES: the whole trail never crosses the wire again.
//
// The record has been written since ADR-0265 (system migration v26) and nothing could read it. This
// panel is the door, and what it must get right is what the record is FOR: answering «who
// authorised that refund on Tuesday» without anybody opening a SQL session against the business's
// own database.
//
//   - the read is PAGED. The audit grows forever by design, so the panel asks the runtime for one
//     page at a time through the list controller and never holds the whole trail (hub#884);
//   - the date range, the pager and the filters are answered BY THE QUERY. Filtering in the client
//     only worked while the complete record was in memory — which was exactly the bug;
//   - every row carries the DOUBLE ATTRIBUTION — who asked and who approved. A list with only one
//     of the two is the exact failure ADR-0265 exists to prevent;
//   - a receipt whose person was deleted still shows, and the absence is NAMED. The query keeps the
//     row on purpose (LEFT JOIN); a blank cell would read as a bug rather than as a fact;
//   - a failed read never reads as «nobody has ever approved anything». Those are opposite answers
//     and only one of them is good news;
//   - only an administrator reads it. Not because the tab is hidden — because the panel does not
//     ask. The runtime gates the query on `hub.administer` and this mirrors it.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const RECORD = [
  {
    id: 'a2',
    command: 'sales.void_line',
    permission: 'sales.void',
    createdBy: 'u-cashier',
    createdByName: 'Marta',
    approvedBy: 'u-manager',
    approvedByName: 'Sofía',
    payloadFingerprint: 'ff01',
    createdAt: '2026-08-11T20:15:00Z',
  },
  {
    id: 'a1',
    command: 'sales.open_drawer',
    permission: 'sales.drawer',
    createdBy: 'u-cashier',
    createdByName: 'Marta',
    approvedBy: 'u-gone',
    approvedByName: '',
    payloadFingerprint: 'ff00',
    createdAt: '2026-08-11T09:02:00Z',
  },
];

// The fake list controller: the panel's whole conversation with the runtime goes through it
// (`lib/approvals.createApprovalsController`), so what these tests pin is WHICH knob the panel
// turns for each table event — the re-query itself is the controller's (SDK) contract.
type Fake = {
  rows: Record<string, unknown>[];
  total: number;
  loading: boolean;
  error: string;
  state: {
    page: number;
    pageSize: number;
    search: string;
    sort?: string;
    dir: 'asc' | 'desc';
    filters: Record<string, unknown>;
    context: Record<string, unknown>;
  };
  onChange: () => void;
  load: ReturnType<typeof vi.fn>;
  setPage: ReturnType<typeof vi.fn>;
  setPageSize: ReturnType<typeof vi.fn>;
  setSort: ReturnType<typeof vi.fn>;
  setSearch: ReturnType<typeof vi.fn>;
  setFilter: ReturnType<typeof vi.fn>;
};

function freshFake(): Fake {
  const fake: Fake = {
    rows: [],
    total: 0,
    loading: false,
    error: '',
    state: { page: 0, pageSize: 10, search: '', sort: 'created_at', dir: 'desc', filters: {}, context: {} },
    onChange: () => {},
    // One page, not the trail: the controller answers with the slice and the real total.
    load: vi.fn(async () => {
      fake.rows = RECORD.map((r) => ({ ...r }));
      fake.total = 41;
      fake.error = '';
      fake.onChange();
    }),
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    setSort: vi.fn(),
    setSearch: vi.fn(),
    setFilter: vi.fn(),
  };
  return fake;
}

let fake: Fake = freshFake();

const createApprovalsController = vi.fn((_client: unknown, onChange: () => void) => {
  fake.onChange = onChange;
  return fake;
});
vi.mock('../lib/approvals', () => ({
  APPROVALS_QUERY: 'hub.approvals.list',
  createApprovalsController: (...a: [unknown, () => void]) => createApprovalsController(...a),
}));

const { getClient } = vi.hoisted(() => ({ getClient: vi.fn(() => ({ queryPage: vi.fn() })) }));
vi.mock('../lib/runtime', () => ({ getClient }));

const { isAdmin } = vi.hoisted(() => ({ isAdmin: { value: true } }));
vi.mock('../lib/session', () => ({ isAdmin }));

vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ApprovalsPanel from './ApprovalsPanel.vue';

// Real strings: what this screen answers is a question in words, so a mute i18n would hide the
// very thing these tests protect.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      employees: { retry: 'Retry' },
      approvals: {
        intro: 'Every approval a manager gave with their PIN, and what it was spent on.',
        search: 'Search approval…',
        colWhen: 'When',
        colApprovedBy: 'Approved by',
        colRequestedBy: 'Asked by',
        colAction: 'Action',
        colLevel: 'Level',
        colFingerprint: 'Reference',
        colRequestedById: 'Asked by (id)',
        colApprovedById: 'Approved by (id)',
        userGone: 'Deleted user',
        empty: 'No approval has been given on this Hub yet.',
        loadError: 'The approval record could not be loaded.',
      },
    },
  },
});

type Column = {
  key: string;
  header: string;
  hidden?: boolean;
  filterable?: boolean;
  filterType?: string;
  sortable?: boolean;
  format?: (row: Record<string, unknown>) => string;
  render?: (row: Record<string, unknown>) => Node;
};
type Panel = VueWrapper<{
  columns: Column[];
  rows: Record<string, unknown>[];
  loadError: boolean;
  load: () => Promise<void>;
}>;

async function mountPanel(): Promise<Panel> {
  const wrapper = mount(ApprovalsPanel, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  }) as unknown as Panel;
  await flushPromises();
  return wrapper;
}

function column(panel: Panel, key: string): Column {
  const col = panel.vm.columns.find((c) => c.key === key);
  if (!col) throw new Error(`the column \`${key}\` is not on the screen`);
  return col;
}

/** What the column `key` shows for the receipt `id`, whether it renders or formats. */
function cellText(panel: Panel, key: string, id: string): string {
  const col = column(panel, key);
  const row = panel.vm.rows.find((r) => r.id === id);
  if (!row) throw new Error(`the receipt \`${id}\` is not in the table`);
  if (col.render) {
    const host = document.createElement('div');
    host.append(col.render(row));
    return host.textContent ?? '';
  }
  return col.format ? col.format(row) : String(row[col.key] ?? '');
}

/** The rendered `<ok-data-table>`, to poke its camelCase CustomEvents at the panel's wiring. */
function table(panel: Panel): HTMLElement {
  const el = panel.find('ok-data-table').element as HTMLElement;
  if (!el) throw new Error('the table is not on the screen');
  return el;
}

function fire(panel: Panel, type: string, detail: unknown): void {
  table(panel).dispatchEvent(new CustomEvent(type, { detail }));
}

beforeEach(() => {
  vi.clearAllMocks();
  isAdmin.value = true;
  fake = freshFake();
});

describe('ApprovalsPanel · the record is read one page at a time', () => {
  it('asks for ONE page on mount, in the order the query gave', async () => {
    const panel = await mountPanel();

    expect(createApprovalsController).toHaveBeenCalledTimes(1);
    expect(fake.load).toHaveBeenCalledTimes(1);
    expect(panel.vm.rows.map((r) => r.id)).toEqual(['a2', 'a1']);
  });

  it('the table is server-side, with the REAL total feeding the pager', async () => {
    const panel = await mountPanel();
    const el = table(panel) as HTMLElement & { total?: number; page?: number };

    // `server-side` is what stops the table from paginating in memory — the whole point of #884.
    expect(el.hasAttribute('server-side')).toBe(true);
    // Two rows on screen, forty-one in the trail: the pager must know the difference.
    expect(el.total).toBe(41);
  });

  it('turning the page asks the CONTROLLER, never the rows in memory', async () => {
    const panel = await mountPanel();

    fire(panel, 'pageChange', 3);
    expect(fake.setPage).toHaveBeenCalledWith(3);

    fire(panel, 'pageSizeChange', 25);
    expect(fake.setPageSize).toHaveBeenCalledWith(25);
  });

  it('the date range travels to the QUERY as the range filter on `created_at`', async () => {
    const panel = await mountPanel();

    fire(panel, 'filterChange', { col: 'createdAt', value: { from: '2026-08-11' } });
    expect(fake.setFilter).toHaveBeenCalledWith('created_at', { from: '2026-08-11' });

    // The `to` edge is made INCLUSIVE for the whole day: the runtime compares RFC 3339 text, and a
    // bare `2026-08-11` would exclude every approval given after midnight — i.e. all of them.
    fire(panel, 'filterChange', { col: 'createdAt', value: { to: '2026-08-11' } });
    expect(fake.setFilter).toHaveBeenCalledWith('created_at', { to: '2026-08-11T23:59:59' });
  });

  it('the action and level filters travel as the query’s exact-match filters', async () => {
    const panel = await mountPanel();

    fire(panel, 'filterChange', { col: 'command', value: 'sales.void_line' });
    expect(fake.setFilter).toHaveBeenCalledWith('command', 'sales.void_line');

    fire(panel, 'filterChange', { col: 'permission', value: 'sales.void' });
    expect(fake.setFilter).toHaveBeenCalledWith('permission', 'sales.void');
  });

  it('the search asks the server — the client no longer holds anything to search in', async () => {
    const panel = await mountPanel();

    fire(panel, 'searchChange', 'Sofía');
    expect(fake.setSearch).toHaveBeenCalledWith('Sofía');
  });

  it('sorting flips the QUERY order of `created_at`, the one sortable column', async () => {
    const panel = await mountPanel();

    expect(column(panel, 'createdAt').sortable).toBe(true);
    fire(panel, 'sortChange', { sort: 'createdAt', dir: 'asc' });
    expect(fake.setSort).toHaveBeenCalledWith('created_at', 'asc');
  });
});

describe('ApprovalsPanel · what the record says', () => {
  it('every row says WHEN, WHO approved, WHO asked and WHAT', async () => {
    const panel = await mountPanel();

    // The double attribution is the point: both people, never one.
    expect(cellText(panel, 'approvedByName', 'a2')).toContain('Sofía');
    expect(cellText(panel, 'createdByName', 'a2')).toContain('Marta');
    expect(cellText(panel, 'command', 'a2')).toContain('sales.void_line');
    expect(cellText(panel, 'permission', 'a2')).toContain('sales.void');
    // The instant, in the reader's locale — a date alone cannot tell two refunds of one shift apart.
    expect(cellText(panel, 'createdAt', 'a2')).toMatch(/2026/);
  });

  it('the date column offers the date-range filter, and keeps the raw instant', async () => {
    const panel = await mountPanel();
    const when = column(panel, 'createdAt');

    expect(when.filterable).toBe(true);
    expect(when.filterType).toBe('daterange');
    // The formatting lives in `render`: a `format` would feed localized text to whatever sorts or
    // exports by value.
    expect(when.format).toBeUndefined();
    expect(when.render).toBeTypeOf('function');
  });

  it('a receipt whose person was deleted is still there, and says so', async () => {
    const panel = await mountPanel();

    expect(panel.vm.rows.map((r) => r.id)).toContain('a1');
    // Not a blank cell: a blank reads as a broken screen, and this is a fact about the hub.
    expect(cellText(panel, 'approvedByName', 'a1')).toContain('Deleted user');
  });

  it('the ids and the fingerprint travel with the table, out of sight but exportable', async () => {
    const panel = await mountPanel();

    // They are what tells two people with one name apart, and WHICH €4 ticket was voided — useless
    // on screen, decisive in an export. The column picker and the CSV carry every column.
    for (const key of ['payloadFingerprint', 'createdBy', 'approvedBy']) {
      expect(column(panel, key).hidden).toBe(true);
    }
  });
});

describe('ApprovalsPanel · what must not be mistaken for silence', () => {
  it('a failed read says «could not load», never «nothing was ever approved»', async () => {
    fake.load.mockImplementation(async () => {
      fake.rows = [];
      fake.total = 0;
      fake.error = 'Failed to fetch';
      fake.onChange();
    });
    const panel = await mountPanel();

    expect(panel.vm.loadError).toBe(true);
    expect(panel.vm.rows).toEqual([]);
    expect(panel.html()).toContain('could not be loaded');
  });

  it('and it can be retried, because the runtime restarting is the usual reason', async () => {
    fake.load.mockImplementationOnce(async () => {
      fake.rows = [];
      fake.error = 'Failed to fetch';
      fake.onChange();
    });
    const panel = await mountPanel();

    await panel.vm.load();

    expect(panel.vm.loadError).toBe(false);
    expect(panel.vm.rows).toHaveLength(2);
  });

  it('an empty record is an ANSWER, and does not raise the error banner', async () => {
    fake.load.mockImplementation(async () => {
      fake.rows = [];
      fake.total = 0;
      fake.error = '';
      fake.onChange();
    });
    const panel = await mountPanel();

    expect(panel.vm.rows).toEqual([]);
    expect(panel.vm.loadError).toBe(false);
    expect(panel.html()).not.toContain('could not be loaded');
  });
});

describe('ApprovalsPanel · only an administrator reads it', () => {
  it('a non-admin never asks the runtime, even if the panel is reached anyway', async () => {
    isAdmin.value = false;

    const panel = await mountPanel();
    await panel.vm.load();

    // Hiding the tab is not a guard: the query is gated on `hub.administer` in the runtime and who
    // approved what is information about the staff, so the shell does not even ask.
    expect(createApprovalsController).not.toHaveBeenCalled();
    expect(fake.load).not.toHaveBeenCalled();
  });

  it('and their empty screen is not an error either: nothing failed', async () => {
    isAdmin.value = false;
    const panel = await mountPanel();

    expect(panel.vm.loadError).toBe(false);
  });
});
