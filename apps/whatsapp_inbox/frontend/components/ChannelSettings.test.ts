// The body of «Channel settings» (WHATSAPP_INBOX-F01, F02, F13, F27): mounted by SettingsPage only for
// whoever configures, so nobody else subscribes to the channel or the templates. Its whole behaviour is
// pinned in pages/SettingsPage.test.ts; here, that it follows both and paints the three blocks.
import { describe, expect, it, vi } from 'vitest';

import { mountInbox } from '../__tests__/mount-inbox';
import ChannelSettings from './ChannelSettings.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

describe('ChannelSettings', () => {
  it('follows the channel and the templates, and paints the number, the month and the templates', async () => {
    const m = await mountInbox(ChannelSettings, { path: '/whatsapp_inbox/settings' });
    await m.live();
    expect(m.params('whatsapp_inbox.channel.get')).toEqual([{}]);
    expect(m.params('whatsapp_inbox.template.list')).toEqual([{ limit: 50, offset: 0 }]);
    await m.result('whatsapp_inbox.channel.get', {
      status: 'not_connected',
      phone_number: '',
      display_name: '',
      monthly_limit: 0,
      monthly_usage: 0,
      cap_reached: false,
      synced_at: null,
      manage_url: 'http://localhost:8001',
      plans_url: 'http://localhost:8001/store/plans',
    });
    expect(m.find('whatsapp-inbox-settings-number').text()).toContain('Not connected');
    expect(m.find('whatsapp-inbox-settings-month').exists()).toBe(true);
    expect(m.find('whatsapp-inbox-templates-title').text()).toBe('Meta templates');
  });
});
