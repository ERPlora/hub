import { describe, expect, it } from 'vitest';

import { YouTubeEmbed } from '@erplora/ui/components';

import type { AppHelp } from '../operations-help';
import { mountBase } from '../__tests__/mount-base';
import HelpContent from './HelpContent.vue';

const help: AppHelp = {
  app: 'table', name: 'Tables', language: 'es', video: null, purpose: 'Para gestionar el comedor.',
  screens: [
    { id: 'floor', title: 'Plano de sala', path: '/table/floor-plan', text: 'Disponible verde; ocupada rojo.' },
    { id: 'settings', title: 'Ajustes', path: '/table/settings', text: 'Configura el comedor.' },
  ],
  flows: [{ id: 'seat', title: 'Sentar un grupo', screens: ['floor'], steps: '1. Toca una mesa.', failure: '' }],
};

async function setup(answer: AppHelp = help) {
  return mountBase(HelpContent, {
    path: '/table/floor-plan', routes: ['/table/floor-plan', '/table/settings'],
    props: { help: answer, current: answer.screens[0], icon: 'ion:grid-outline' },
  });
}

describe('HelpContent', () => {
  it('orders the text sections and marks the current screen', async () => {
    const m = await setup();
    expect(m.wrapper.findAll('[data-help-section]').map((section) => section.attributes('data-help-section'))).toEqual([
      'purpose', 'current', 'flows', 'screens',
    ]);
    expect(m.wrapper.get('[data-testid="help-current-screen"]').text()).toContain('Plano de sala');
    expect(m.wrapper.get('[data-testid="help-current-screen"]').text()).toContain('You are here');
    expect(m.wrapper.get('[data-testid="help-current-screen"]').text()).toContain('Disponible verde; ocupada rojo.');
  });

  it('sets the content language reported by the answer', async () => {
    const m = await setup();
    expect(m.wrapper.get('[data-testid="help-content"]').attributes('lang')).toBe('es');
  });

  it('leaves no video block when the answer has none', async () => {
    const m = await setup();
    expect(m.wrapper.findComponent(YouTubeEmbed).exists()).toBe(false);
    expect(m.wrapper.find('[data-help-section="video"]').exists()).toBe(false);
  });

  it('puts the app video first with its title and icon when present', async () => {
    const m = await setup({ ...help, video: 'dQw4w9WgXcQ' });
    expect(m.wrapper.findAll('[data-help-section]')[0].attributes('data-help-section')).toBe('video');
    const video = m.wrapper.getComponent(YouTubeEmbed);
    expect(video.props()).toMatchObject({ videoId: 'dQw4w9WgXcQ', title: 'How Tables works', icon: 'ion:grid-outline' });
    expect(video.props('duration')).toBeUndefined();
  });

  it('keeps other screens collapsed until their button is pressed', async () => {
    const m = await setup();
    const button = m.wrapper.get('[data-testid="help-other-screen-settings"]');
    expect(button.attributes('aria-expanded')).toBe('false');
    expect(m.wrapper.find('[data-testid="help-other-screen-content-settings"]').exists()).toBe(false);
    await button.trigger('click');
    expect(button.attributes('aria-expanded')).toBe('true');
    expect(m.wrapper.get('[data-testid="help-other-screen-content-settings"]').text()).toContain('Configura el comedor.');
  });

  it('omits the how-to section when the module has no flows', async () => {
    const m = await setup({ ...help, flows: [] });
    expect(m.wrapper.find('[data-help-section="flows"]').exists()).toBe(false);
  });
});
