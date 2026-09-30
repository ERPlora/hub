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

// hub#2255 — an answer that refuses (403, 5xx) is not a lost connection: the notice says the
// business is not available, that this device has nothing to check, and that it keeps trying.
describe('BootUnreachable when the hub refuses (hub#2255)', () => {
  it('says the business is not available and does not send the person to check the connection', () => {
    const w = mount(BootUnreachable, { props: { failure: 'refused' }, global: { plugins: [i18n] } });

    const notice = w.find('[data-testid="boot-unreachable"]');
    expect(notice.attributes('data-failure')).toBe('refused');
    expect(notice.attributes('heading')).toBe(i18n.global.t('boot.refused.title'));
    expect(notice.attributes('message')).toBe(i18n.global.t('boot.refused.body', { seconds: 30 }));
    expect(notice.attributes('message')).not.toBe(i18n.global.t('boot.unreachable.body'));
    // The crossed-out cloud says «no connection»: the wrong picture for a refusal.
    expect(notice.attributes('icon')).not.toBe('cloud-offline-outline');
    expect(w.find('[data-testid="boot-unreachable-retry"]').text()).toBe(i18n.global.t('boot.refused.retry'));
  });

  it('without a reason it is still the lost-connection notice of hub#2143', () => {
    const w = mount(BootUnreachable, { global: { plugins: [i18n] } });

    const notice = w.find('[data-testid="boot-unreachable"]');
    expect(notice.attributes('data-failure')).toBe('unreachable');
    expect(notice.attributes('icon')).toBe('cloud-offline-outline');
  });

  it('has its refusal words in English and in Spanish, with the wait in the sentence', () => {
    for (const key of ['title', 'body', 'retry'] as const) {
      const enText = (en as any).boot?.refused?.[key];
      const esText = (es as any).boot?.refused?.[key];
      expect(typeof enText).toBe('string');
      expect(typeof esText).toBe('string');
      expect(enText).not.toBe(esText);
    }
    expect((en as any).boot.refused.body).toContain('{seconds}');
    expect((es as any).boot.refused.body).toContain('{seconds}');
  });
});
