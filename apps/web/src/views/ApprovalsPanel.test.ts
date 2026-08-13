// @vitest-environment happy-dom
// hub#512 — the screen that finally reads the PIN approval record (People › Approvals).
//
// The record has been written since ADR-0265 (system migration v26) and nothing could read it. This
// panel is the door, and what it must get right is what the record is FOR: answering «who
// authorised that refund on Tuesday» without anybody opening a SQL session against the business's
// own database.
//
//   - every row carries the DOUBLE ATTRIBUTION — who asked and who approved. A list with only one
//     of the two is the exact failure ADR-0265 exists to prevent;
//   - the date column keeps the RAW instant. `ok-data-table` reads `format` as the value it filters
//     and sorts by, so a column that formats the date for the eye makes the date-range filter match
//     nothing — on the one screen whose whole job is «show me that Tuesday»;
//   - a receipt whose person was deleted still shows, and the absence is NAMED. The query keeps the
//     row on purpose (LEFT JOIN); a blank cell would read as a bug rather than as a fact;
//   - a failed read never reads as «nobody has ever approved anything». Those are opposite answers
//     and only one of them is good news;
//   - only an administrator reads it. Not because the tab is hidden — because the panel does not
//     ask. The runtime gates the query on `hub.administer` and this mirrors it.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const listApprovals = vi.fn();
vi.mock('../lib/approvals', () => ({
  APPROVALS_QUERY: 'hub.approvals.list',
  listApprovals: (...a: unknown[]) => listApprovals(...a),
}));

const { getClient } = vi.hoisted(() => ({ getClient: vi.fn(() => ({ query: vi.fn() })) }));
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

type Column = {
  key: string;
  header: string;
  hidden?: boolean;
  filterable?: boolean;
  filterType?: string;
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

beforeEach(() => {
  vi.clearAllMocks();
  isAdmin.value = true;
  listApprovals.mockResolvedValue(RECORD.map((r) => ({ ...r })));
});

describe('ApprovalsPanel · the record can finally be read', () => {
  it('reads it on mount, in the order the query gave', async () => {
    const panel = await mountPanel();

    expect(listApprovals).toHaveBeenCalledTimes(1);
    expect(panel.vm.rows.map((r) => r.id)).toEqual(['a2', 'a1']);
  });

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

  it('the date column can actually be filtered by date', async () => {
    const panel = await mountPanel();
    const when = column(panel, 'createdAt');

    expect(when.filterable).toBe(true);
    expect(when.filterType).toBe('daterange');
    // `ok-data-table` filters and sorts by `format(row)` when a column has one, so formatting the
    // date here would feed the range filter a localized string, `new Date()` would return NaN, and
    // «show me that Tuesday» would answer nothing. The formatting lives in `render`.
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
    listApprovals.mockRejectedValue(new Error('Failed to fetch'));
    const panel = await mountPanel();

    expect(panel.vm.loadError).toBe(true);
    expect(panel.vm.rows).toEqual([]);
    expect(panel.html()).toContain('could not be loaded');
  });

  it('and it can be retried, because the runtime restarting is the usual reason', async () => {
    listApprovals.mockRejectedValue(new Error('Failed to fetch'));
    const panel = await mountPanel();

    listApprovals.mockResolvedValue(RECORD.map((r) => ({ ...r })));
    await panel.vm.load();

    expect(panel.vm.loadError).toBe(false);
    expect(panel.vm.rows).toHaveLength(2);
  });

  it('an empty record is an ANSWER, and does not raise the error banner', async () => {
    listApprovals.mockResolvedValue([]);
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
    expect(listApprovals).not.toHaveBeenCalled();
  });

  it('and their empty screen is not an error either: nothing failed', async () => {
    isAdmin.value = false;
    const panel = await mountPanel();

    expect(panel.vm.loadError).toBe(false);
  });
});
