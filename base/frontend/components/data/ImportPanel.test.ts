// Settings › Data › Import (BASE-G103–G107), end to end over the fake API: only an administrator reads it; the last
// import that did not go in whole opens first (its report, «Retry what is missing», «See the templates»); otherwise
// the catalogue and «Upload from file» → review → import → report. A file or template that cannot be read says why
// and stays on the choice; an import refused stays on the review with the reason.
import { afterEach, describe, expect, it } from 'vitest';

import { load, summary, template } from '../../__tests__/data-fixtures';
import { EMPLOYEE, flush, mountBase } from '../../__tests__/mount-base';
import type { ImportRow } from '../../operations';
import { SESSION_CHANGED } from '../../lib/access';
import ImportPanel from './ImportPanel.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

type Calls = { url: string; body: unknown }[];

function api(answers: Record<string, () => Response>, calls: Calls) {
  return async ({ url, init }: { url: string; init: RequestInit }) => {
    calls.push({ url, body: init.body ? JSON.parse(String(init.body)) : undefined });
    const path = url.split('?')[0];
    return answers[path]?.() ?? Response.json({ error: { code: 'not_found', message: 'nope' } }, { status: 404 });
  };
}

const refused = (message: string) => () =>
  Response.json({ error: { code: 'invalid_payload', message } }, { status: 422 });

const UNFINISHED: ImportRow = load({
  status: 'partial',
  retry: true,
  retry_blocked: '',
  report: { status: 'partial', dropped: [], apps: [{ id: 'table', label: 'Tables', status: 'failed', datasets: [] }] },
});

async function panel(answers: Record<string, () => Response> = {}, imports: { imports: ImportRow[]; unfinished: ImportRow | null } = { imports: [], unfinished: null }) {
  const calls: Calls = [];
  const m = await mountBase(ImportPanel, { path: '/settings#data', routes: ['/settings'], onApi: api(answers, calls) });
  const call = await m.live();
  await m.result(call, 'base.import.list', imports);
  await m.result(call, 'base.blueprint.list', { templates: [template('restaurant.es')], empty: true });
  return { ...m, call, calls };
}

async function settle() {
  for (let i = 0; i < 4; i += 1) await flush();
}

describe('ImportPanel', () => {
  it('to a person who does not administer the hub, says only an administrator can, and asks nothing', async () => {
    const m = await mountBase(ImportPanel, { session: EMPLOYEE });
    expect(m.wrapper.text()).toContain('Only an administrator can see and import templates.');
    expect(m.client.stream.subscriptions('base.blueprint.list')).toEqual([]);
    expect(m.client.stream.subscriptions('base.import.list')).toEqual([]);
  });

  it('says what it does and offers the catalogue and «Upload from file»', async () => {
    const m = await panel();
    expect(m.wrapper.text()).toContain('Load a template: it fills your apps with its data');
    expect(m.wrapper.get('h3').text()).toBe('Choose what to load');
    expect(m.wrapper.get('[data-testid="import-upload"]').text()).toBe('Upload from file');
    expect(m.wrapper.find('[data-testid="templates-row"]').exists()).toBe(true);
  });

  it('a template: reviews it, imports the apps ticked and shows the report', async () => {
    const m = await panel({
      '/api/settings/data/blueprints/inspect': () => Response.json(summary()),
      '/api/settings/data/blueprints/import': () => Response.json(load()),
    });
    await m.wrapper.get('[data-testid="templates-row-restaurant.es-use"]').trigger('click');
    await settle();
    expect(m.calls.at(-1)).toEqual({ url: '/api/settings/data/blueprints/inspect', body: { template: 'restaurant.es' } });
    expect(m.wrapper.find('[data-testid="review"]').exists()).toBe(true);
    await m.wrapper.get('[data-testid="review-import"]').trigger('click');
    await settle();
    expect(m.calls.at(-1)).toEqual({
      url: '/api/settings/data/blueprints/import',
      body: { template: 'restaurant.es', apps: ['inventory', 'customer'] },
    });
    expect(m.wrapper.get('[data-testid="report-status"]').text()).toContain('Everything went in.');
    await m.wrapper.get('[data-testid="report-templates"]').trigger('click');
    await settle();
    expect(m.wrapper.find('[data-testid="templates-row"]').exists()).toBe(true);
  });

  it('reads the session again after a load or a retry: the apps it turned on reach the menu (round 2026-10-27)', async () => {
    let read = 0;
    const count = () => (read += 1);
    window.addEventListener(SESSION_CHANGED, count);
    try {
      const m = await panel(
        {
          '/api/settings/data/blueprints/inspect': () => Response.json(summary()),
          '/api/settings/data/blueprints/import': () => Response.json(load({ id: 'again' })),
        },
        { imports: [UNFINISHED], unfinished: UNFINISHED },
      );
      await m.wrapper.get('[data-testid="report-retry"]').trigger('click');
      await settle();
      expect(read).toBe(1);
      await m.wrapper.get('[data-testid="report-templates"]').trigger('click');
      await settle();
      await m.wrapper.get('[data-testid="templates-row-restaurant.es-use"]').trigger('click');
      await settle();
      expect(read).toBe(1); // reviewing writes nothing
      await m.wrapper.get('[data-testid="review-import"]').trigger('click');
      await settle();
      expect(read).toBe(2);
    } finally {
      window.removeEventListener(SESSION_CHANGED, count);
    }
  });

  it('an import refused does not read the session again', async () => {
    let read = 0;
    const count = () => (read += 1);
    window.addEventListener(SESSION_CHANGED, count);
    try {
      const m = await panel({
        '/api/settings/data/blueprints/inspect': () => Response.json(summary()),
        '/api/settings/data/blueprints/import': refused('The app refused it.'),
      });
      await m.wrapper.get('[data-testid="templates-row-restaurant.es-use"]').trigger('click');
      await settle();
      await m.wrapper.get('[data-testid="review-import"]').trigger('click');
      await settle();
      expect(read).toBe(0);
    } finally {
      window.removeEventListener(SESSION_CHANGED, count);
    }
  });

  it('a template that cannot be read says why and stays on the choice', async () => {
    const m = await panel({ '/api/settings/data/blueprints/inspect': refused('This template is not in the catalogue.') });
    await m.wrapper.get('[data-testid="templates-row-restaurant.es-use"]').trigger('click');
    await settle();
    expect(m.wrapper.get('[data-testid="import-read-error"]').text()).toContain(
      'The file could not be read: This template is not in the catalogue.',
    );
    expect(m.wrapper.find('[data-testid="templates-row"]').exists()).toBe(true);
  });

  it('a file: reads it in base64 and reviews it; one over 20 MB is refused before it is sent', async () => {
    const m = await panel({ '/api/settings/data/blueprints/inspect': () => Response.json(summary({ source: 'file' })) });
    const input = m.wrapper.get('[data-testid="import-file"]').element as HTMLInputElement;
    // What the page writes in the input's value: a file input only takes '' (emptied for the same file again).
    const written: string[] = [];
    Object.defineProperty(input, 'value', { get: () => 'C:\\fakepath\\chosen.zip', set: (value: string) => void written.push(value), configurable: true });
    // INVENTORY-F33: 20 MB, so 300 photos of its own fit (base.blueprint.MAX_FILE_BYTES).
    const big = new File([new Uint8Array(4)], 'big.blueprint.zip');
    Object.defineProperty(big, 'size', { value: 20 * 1024 * 1024 + 1 });
    Object.defineProperty(input, 'files', { value: [big], configurable: true });
    input.dispatchEvent(new Event('change'));
    await settle();
    expect(m.wrapper.get('[data-testid="import-read-error"]').text()).toContain('the file is larger than 20 MB.');
    expect(m.calls).toEqual([]);
    const small = new File([new Uint8Array([80, 75, 3, 4])], 'mine.blueprint.zip');
    Object.defineProperty(input, 'files', { value: [small], configurable: true });
    input.dispatchEvent(new Event('change'));
    await settle();
    expect(m.calls.at(-1)).toEqual({ url: '/api/settings/data/blueprints/inspect', body: { file_base64: 'UEsDBA==' } });
    expect(m.wrapper.find('[data-testid="review"]').exists()).toBe(true);
    // The same file can be chosen again after an error: the input is emptied each time.
    expect(written).toEqual(['', '']);
  });

  it('an import refused stays on the review with the reason', async () => {
    const m = await panel({
      '/api/settings/data/blueprints/inspect': () => Response.json(summary()),
      '/api/settings/data/blueprints/import': refused('The app refused it.'),
    });
    await m.wrapper.get('[data-testid="templates-row-restaurant.es-use"]').trigger('click');
    await settle();
    await m.wrapper.get('[data-testid="review-import"]').trigger('click');
    await settle();
    expect(m.wrapper.get('[data-testid="review-error"]').text()).toContain('The import failed: The app refused it.');
  });

  it('opens with the last import that did not go in whole, retries it and goes on to the catalogue', async () => {
    const m = await panel(
      { '/api/settings/data/blueprints/import': () => Response.json(load({ id: 'again' })) },
      { imports: [UNFINISHED], unfinished: UNFINISHED },
    );
    expect(m.wrapper.find('[data-testid="report-unfinished"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="templates-row"]').exists()).toBe(false);
    await m.wrapper.get('[data-testid="report-retry"]').trigger('click');
    await settle();
    expect(m.calls.at(-1)).toEqual({ url: '/api/settings/data/blueprints/import', body: { retry_of: UNFINISHED.id } });
    expect(m.wrapper.get('[data-testid="report-status"]').text()).toContain('Everything went in.');
    await m.wrapper.get('[data-testid="report-templates"]').trigger('click');
    await settle();
    expect(m.wrapper.find('[data-testid="templates-row"]').exists()).toBe(true);
  });
});
