// @vitest-environment happy-dom
// hub#2143 — the notice painted when the hub does not answer at boot: what happened, in the
// person's language, and one way forward.
import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';

import BootUnreachable from './BootUnreachable.vue';
import { i18n } from '../i18n';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

describe('BootUnreachable (hub#2143)', () => {
  it('says the business cannot be reached, and offers to try again', async () => {
    const w = mount(BootUnreachable, { global: { plugins: [i18n] } });

    const notice = w.find('[data-testid="boot-unreachable"]');
    expect(notice.exists()).toBe(true);
    expect(notice.attributes('heading')).toBe(i18n.global.t('boot.unreachable.title'));
    expect(notice.attributes('message')).toBe(i18n.global.t('boot.unreachable.body'));

    const retry = w.find('[data-testid="boot-unreachable-retry"]');
    expect(retry.text()).toBe(i18n.global.t('boot.unreachable.retry'));
    await retry.trigger('click');
    expect(w.emitted('retry')).toHaveLength(1);
  });

  it('has its words in English and in Spanish', () => {
    for (const key of ['title', 'body', 'retry'] as const) {
      const enText = (en as any).boot?.unreachable?.[key];
      const esText = (es as any).boot?.unreachable?.[key];
      expect(typeof enText).toBe('string');
      expect(typeof esText).toBe('string');
      expect(enText).not.toBe(esText);
    }
  });
});
