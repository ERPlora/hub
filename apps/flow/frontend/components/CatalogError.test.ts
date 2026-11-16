// What automations can use here (the catalog) that could not be read, said in red with «Retry» (WORKBOOK «Estados de
// cada pantalla · Error»): the page, the editor and «Which data?» say it with this one block (hub#969).
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { click, mountFlow, settle } from '../__tests__/mount-flow';
import CatalogError from './CatalogError.vue';

async function setup(props: Record<string, unknown>) {
  const m = await mountFlow(CatalogError, { props });
  await settle();
  return m;
}

describe('CatalogError', () => {
  it('says the catalog could not be read in red, never the technical text, and «Retry» asks to read it again', async () => {
    const m = await setup({ error: new ApiError(500, 'internal_error', 'Internal error') });
    expect(m.find('flow-catalog-error').text()).toContain('What automations can use here could not be read.');
    expect(m.find('flow-catalog-error').text()).not.toContain('Internal error');
    expect(m.find('flow-catalog-error').attributes('data-tone')).toBe('danger');
    expect(m.find('flow-catalog-retry').text()).toBe('Retry');
    await click(m.find('flow-catalog-retry').element);
    expect(m.wrapper.emitted('retry')).toEqual([[]]);
  });

  it('adds the reason the Hub gave in words', async () => {
    const m = await setup({ error: new ApiError(403, 'forbidden', 'You cannot see this.') });
    expect(m.find('flow-catalog-error').text()).toContain('What automations can use here could not be read. You cannot see this.');
  });

  it('takes the test names of where it is said', async () => {
    const m = await setup({ error: new ApiError(500, 'internal_error', ''), testid: 'flow-picker' });
    expect(m.find('flow-picker-error').exists()).toBe(true);
    expect(m.find('flow-picker-retry').exists()).toBe(true);
    expect(m.find('flow-catalog-error').exists()).toBe(false);
  });
});
