// «Import report» (BASE-G106) and the last one that did not go in whole (BASE-G107): how it went, app by app and part
// by part in words — «Applied», «You had it already», «Applied in part», «Failed» with what went wrong, an app off —,
// what was left out on purpose, «Retry what is missing» when it can (or why it cannot), «See the templates» and «Go
// to Home». A status this screen does not know is painted as «Failed» with its own text, never as a success.
import { afterEach, describe, expect, it } from 'vitest';

import { load } from '../../__tests__/data-fixtures';
import { flush, mountBase } from '../../__tests__/mount-base';
import type { ImportRow } from '../../operations';
import ImportReport from './ImportReport.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

const PARTIAL: Partial<ImportRow> = {
  status: 'partial',
  retry: true,
  retry_blocked: '',
  report: {
    status: 'partial',
    dropped: ['People and their PINs'],
    apps: [
      {
        id: 'inventory',
        label: 'Inventory',
        status: 'partial',
        datasets: [
          {
            key: 'inventory.product',
            label: 'Products',
            rows: 12,
            status: 'partial',
            created: 10,
            already: 1,
            failed: 1,
            problems: ['«Cola»: the price is not valid'],
          },
        ],
      },
      { id: 'table', label: 'Tables', status: 'already', datasets: [] },
      { id: 'kitchen', label: 'Kitchen', status: 'inactive', datasets: [] },
      { id: 'weird', label: 'Weird', status: 'exploded' as never, datasets: [] },
    ],
  },
};

async function report(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountBase(ImportReport, { props: { load: load(), ...props }, locale, path: '/settings#data', routes: ['/settings'] });
}

const pills = (m: Awaited<ReturnType<typeof report>>) =>
  m.wrapper.findAll('[data-testid="report-app"]').map((row) => [row.attributes('data-id'), row.get('.status-pill, [data-testid="report-app-status"]').text()]);

describe('ImportReport', () => {
  it('says everything went in, app by app, part by part', async () => {
    const m = await report();
    expect(m.wrapper.get('[data-testid="report-status"]').text()).toContain('Everything went in.');
    expect(pills(m)).toEqual([['inventory', 'Applied']]);
    expect(m.wrapper.text()).toContain('12 created · 0 already there · 0 failed');
    expect(m.wrapper.find('[data-testid="report-retry"]').exists()).toBe(false);
  });

  it('paints each status in words; one it does not know as «Failed» with its own text', async () => {
    const m = await report({ load: load(PARTIAL) }, 'es');
    expect(m.wrapper.get('[data-testid="report-status"]').text()).toContain('No todo entró.');
    expect(pills(m)).toEqual([
      ['inventory', 'Aplicado en parte'],
      ['table', 'Ya lo tenías'],
      ['kitchen', 'App desactivada'],
      ['weird', 'Falló'],
    ]);
    expect(m.wrapper.get('[data-id="weird"]').text()).toContain('exploded');
    expect(m.wrapper.text()).toContain('«Cola»: the price is not valid');
    expect(m.wrapper.get('[data-testid="report-dropped"]').text()).toContain('People and their PINs');
  });

  it('heads the last unfinished import with its name and date', async () => {
    const m = await report({ load: load(PARTIAL), unfinished: true });
    expect(m.wrapper.get('[data-testid="report-unfinished"]').text()).toMatch(
      /This is the report of your last import of Restaurant \(.*2026.*\)\. Not everything went in\./,
    );
  });

  it('retries what is missing, says it works meanwhile and why it failed', async () => {
    const m = await report({ load: load(PARTIAL) });
    await m.wrapper.get('[data-testid="report-retry"]').trigger('click');
    expect(m.wrapper.emitted('retry')).toHaveLength(1);
    await m.wrapper.setProps({ retrying: true });
    const button = m.wrapper.get('[data-testid="report-retry"]');
    expect(button.text()).toBe('Retrying…');
    expect((button.element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    await m.wrapper.setProps({ retrying: false, retryError: 'The catalogue is gone.' });
    expect(m.wrapper.get('[data-testid="report-retry-error"]').text()).toContain('The retry failed: The catalogue is gone.');
  });

  it('cannot retry a file uploaded by hand nor a template whose version is gone, and says why', async () => {
    const file = await report({ load: load({ ...PARTIAL, retry: false, retry_blocked: 'file', source: 'file' }) });
    const button = file.wrapper.get('[data-testid="report-retry"]');
    expect((button.element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    expect(file.wrapper.get('[data-testid="report-retry-blocked"]').text()).toContain('uploaded by hand');
    file.wrapper.unmount();
    const gone = await report({ load: load({ ...PARTIAL, retry: false, retry_blocked: 'version_gone' }) });
    expect(gone.wrapper.get('[data-testid="report-retry-blocked"]').text()).toContain('no longer in the catalogue');
  });

  it('goes back to the templates, or to the Home', async () => {
    const m = await report();
    await m.wrapper.get('[data-testid="report-templates"]').trigger('click');
    expect(m.wrapper.emitted('templates')).toHaveLength(1);
    await m.wrapper.get('[data-testid="report-home"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/');
  });
});
