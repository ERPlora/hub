// `useLiveList`: a list query followed live in WINDOWS of at most 100 rows (the server's cap on
// `limit`), each its own subscription, merged into one page for the DataTable: the rows in order, the
// total of the query, «loading» until every window answered, the first error. Fewer windows release the
// subscriptions left over.
import { describe, expect, it } from 'vitest';
import { defineComponent, h, type PropType } from 'vue';

import { errorFrame, flush, mountInbox } from '../__tests__/mount-inbox';
import type { TemplateOut } from '../operations';
import type { ListWindow } from './useServerTable';
import { useLiveList } from './useLiveList';

const OP = 'whatsapp_inbox.template.list';

const template = (n: number): TemplateOut => ({
  id: `t${n}`,
  name: `template_${n}`,
  language: 'es',
  category: 'UTILITY',
  status: 'APPROVED',
  header: '',
  body: 'Hola {{1}}',
  footer: '',
  variables: 1,
  rejected_reason: '',
  synced_at: null,
  header_format: '',
  body_examples: [],
  buttons: [],
  meta_id: '',
  draft: null,
  submit_state: '',
  submit_error_code: '',
  submit_error: '',
  editable: true,
  sendable: true,
  supported: true,
  deleting: false,
});
const rows = (from: number, count: number) => Array.from({ length: count }, (_, i) => template(from + i));

/** The list the host component made (its refs, not the component's unwrapped proxy). */
let captured: ReturnType<typeof useLiveList<typeof OP>> | undefined;

const Host = defineComponent({
  props: { windows: { type: Array as PropType<ListWindow[]>, required: true } },
  setup(props) {
    captured = useLiveList(OP, () => ({ search: 'record' }), () => props.windows);
    return () => h('div');
  },
});

async function setup(windows: ListWindow[]) {
  const m = await mountInbox(Host, { props: { windows } });
  await m.live();
  return { ...m, list: captured! };
}

describe('useLiveList', () => {
  it('one window is one subscription, and its page is the list', async () => {
    const s = await setup([{ limit: 50, offset: 0 }]);
    expect(s.params(OP)).toEqual([{ search: 'record', limit: 50, offset: 0 }]);
    expect(s.list.status.value).toBe('loading');
    await s.result(OP, { rows: rows(0, 2), total: 2, limit: 50, offset: 0 });
    expect(s.list.status.value).toBe('live');
    expect(s.list.data.value).toEqual({ rows: rows(0, 2), total: 2, limit: 50, offset: 0 });
  });

  it('several windows: one subscription each, never over 100, merged in order once all answered', async () => {
    const s = await setup([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
      { limit: 50, offset: 200 },
    ]);
    expect(s.params(OP)).toEqual([
      { search: 'record', limit: 100, offset: 0 },
      { search: 'record', limit: 100, offset: 100 },
      { search: 'record', limit: 50, offset: 200 },
    ]);
    await s.result(OP, { rows: rows(0, 100), total: 230, limit: 100, offset: 0 }, { offset: 0 });
    await s.result(OP, { rows: rows(100, 100), total: 230, limit: 100, offset: 100 }, { offset: 100 });
    expect(s.list.status.value, 'a window has not answered yet').toBe('loading');
    expect(s.list.data.value?.rows).toHaveLength(200);
    await s.result(OP, { rows: rows(200, 30), total: 230, limit: 50, offset: 200 }, { offset: 200 });
    expect(s.list.status.value).toBe('live');
    const page = s.list.data.value!;
    expect([page.rows.length, page.total, page.limit, page.offset]).toEqual([230, 230, 250, 0]);
    expect(page.rows.map((r) => r.id)).toEqual(rows(0, 230).map((r) => r.id));
  });

  it('a window added after mounting («Load more») is a subscription more, on the same live client', async () => {
    const s = await setup([{ limit: 100, offset: 0 }]);
    await s.result(OP, { rows: rows(0, 100), total: 150, limit: 100, offset: 0 });
    await s.wrapper.setProps({
      windows: [
        { limit: 100, offset: 0 },
        { limit: 100, offset: 100 },
      ],
    });
    await s.reopen();
    expect(s.params(OP).map((p) => p.offset)).toEqual([0, 100]);
    await s.result(OP, { rows: rows(0, 100), total: 150, limit: 100, offset: 0 }, { offset: 0 });
    await s.result(OP, { rows: rows(100, 50), total: 150, limit: 100, offset: 100 }, { offset: 100 });
    expect(s.list.data.value?.rows).toHaveLength(150);
  });

  it('back to one window, the others are released', async () => {
    const s = await setup([
      { limit: 100, offset: 0 },
      { limit: 20, offset: 100 },
    ]);
    await s.wrapper.setProps({ windows: [{ limit: 50, offset: 0 }] });
    await flush();
    await s.clock.advance(2500);
    expect(s.params(OP)).toEqual([{ search: 'record', limit: 50, offset: 0 }]);
  });

  it('an error in any window is the list’s error', async () => {
    const s = await setup([
      { limit: 100, offset: 0 },
      { limit: 20, offset: 100 },
    ]);
    s.net.lastStream().push(errorFrame(s.subId(OP, { offset: 100 }), 'whatsapp_inbox.boom'));
    await flush();
    expect([s.list.status.value, s.list.error.value?.code]).toEqual(['error', 'whatsapp_inbox.boom']);
  });
});
