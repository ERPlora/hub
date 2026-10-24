// BASE-G113 and G114: an answer painted with its format — never as HTML —, its links only to screens this hub serves,
// named as the menu names them; a table scrolls inside its own box.
import { describe, expect, it } from 'vitest';

import { mountBase } from '../../__tests__/mount-base';
import AssistantMarkdown from './AssistantMarkdown.vue';

function mountText(text: string) {
  return mountBase(AssistantMarkdown, {
    props: {
      text,
      screenExists: (path: string) => path.startsWith('/settings') || path === '/customer/customers',
      nameOf: (path: string) => (path === '/customer/customers' ? 'Clientes' : undefined),
    },
  });
}

describe('AssistantMarkdown', () => {
  it('paints bold, lists and a table in its own scrolling box', async () => {
    const { wrapper } = await mountText('**Hoy**\n\n- Uno\n- Dos\n\n| A | B |\n|---|---|\n| 1 | 2 |');
    expect(wrapper.find('strong').text()).toBe('Hoy');
    expect(wrapper.findAll('li').map((li) => li.text())).toEqual(['Uno', 'Dos']);
    expect(wrapper.find('.assistant-table table th').text()).toBe('A');
    wrapper.unmount();
  });

  it('never turns what the model writes into HTML', async () => {
    const { wrapper } = await mountText('<img src=x onerror=alert(1)> **ok**');
    expect(wrapper.find('img').exists()).toBe(false);
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>');
    wrapper.unmount();
  });

  it('a link to a screen of this hub leads there; a bare path is named as the menu names it', async () => {
    const { wrapper } = await mountText('Ve a [tus ajustes](/settings#business) o a /customer/customers.');
    const links = wrapper.findAll('a.assistant-link');
    expect(links.map((link) => [link.text(), link.attributes('href')])).toEqual([
      ['tus ajustes', '/settings#business'],
      ['Clientes', '/customer/customers'],
    ]);
    await links[0].trigger('click');
    expect(wrapper.emitted('go')).toEqual([['/settings#business']]);
    wrapper.unmount();
  });

  it('a screen this hub does not serve is plain text, no link', async () => {
    const { wrapper } = await mountText('Mira [informes](/reports).');
    expect(wrapper.find('a').exists()).toBe(false);
    expect(wrapper.text()).toBe('Mira informes.');
    wrapper.unmount();
  });
});
