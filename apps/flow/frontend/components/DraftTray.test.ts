// «Proposed by the assistant» (WORKBOOK FLOW-F18, F19): the drafts waiting for a person, live; «Review»
// opens one in the editor as an automation that does not exist yet; × discards it at once. With no
// draft the section does not show.
import { describe, expect, it, vi } from 'vitest';

import type { DraftOut } from '../operations';
import { click, mountFlow, settle } from '../__tests__/mount-flow';
import DraftTray from './DraftTray.vue';

const toastSuccess = vi.hoisted(() => vi.fn<(message: string) => Promise<void>>(async () => undefined));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({ ...(await importOriginal<typeof import('@erplora/ui/shell')>()), toastSuccess }));

const OP = 'flow.draft.list';
const draft = (id: string, name: string): DraftOut => ({
  id,
  name,
  definition: { steps: [] },
  notes: [],
  status: 'pending',
  flow_id: null,
  created_at: '2026-10-15T10:00:00+02:00',
  created_by: 'ana',
});

async function setup(rows: DraftOut[], answer: [number, unknown] = [200, { ...draft('d1', 'x'), status: 'dismissed' }]) {
  const m = await mountFlow(DraftTray, { answers: { '/api/flow/drafts/dismiss': answer } });
  await m.live();
  await m.result(OP, { rows, total: rows.length, limit: 50, offset: 0 });
  return m;
}

describe('DraftTray', () => {
  it('hides itself when nothing waits', async () => {
    const m = await setup([]);
    expect(m.find('flow-drafts').exists()).toBe(false);
  });

  it('lists the drafts with their badge', async () => {
    const m = await setup([draft('d1', 'Call who did not come')]);
    expect(m.find('flow-drafts').text()).toContain('Proposed by the assistant');
    expect(m.find('flow-draft-d1').text()).toContain('Call who did not come');
    expect(m.find('flow-draft-d1').text()).toContain('Draft');
  });

  it('«Review» opens it in the editor', async () => {
    const m = await setup([draft('d1', 'A')]);
    await click(m.find('flow-draft-review-d1').element);
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/flow/automations/new?draft=d1');
  });

  it('× discards it, and a refusal is said', async () => {
    const m = await setup([draft('d1', 'A')]);
    await click(m.find('flow-draft-dismiss-d1').element);
    await settle();
    expect(m.sent().map((call) => [call.path, call.body])).toEqual([['/api/flow/drafts/dismiss', { id: 'd1' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Discarded.');
    const refused = await setup([draft('d1', 'A')], [409, { error: { code: 'flow.draft_decided', message: 'That draft was already decided.' } }]);
    await click(refused.find('flow-draft-dismiss-d1').element);
    await settle();
    expect(refused.find('flow-drafts-error').text()).toContain('That draft was already decided.');
  });
});
