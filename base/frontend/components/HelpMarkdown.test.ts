import { describe, expect, it } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import HelpMarkdown from './HelpMarkdown.vue';

describe('HelpMarkdown', () => {
  it('renders markdown as Vue elements rather than raw HTML', async () => {
    const m = await mountBase(HelpMarkdown, { props: { text: '**Safe** <img src=x onerror=alert(1)>' } });
    expect(m.wrapper.find('strong').text()).toBe('Safe');
    expect(m.wrapper.find('img').exists()).toBe(false);
    expect(m.wrapper.text()).toContain('<img src=x onerror=alert(1)>');
  });

  it('emits navigation for a link to a known screen', async () => {
    const m = await mountBase(HelpMarkdown, {
      path: '/table/floor-plan',
      routes: ['/table/floor-plan', '/table/settings'],
      props: { text: '[Open settings](/table/settings)' },
    });
    await m.wrapper.get('a').trigger('click');
    await flush();
    expect(m.wrapper.emitted('go')).toEqual([['/table/settings']]);
  });
});
