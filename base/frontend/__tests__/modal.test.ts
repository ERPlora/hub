import { describe, expect, it } from 'vitest';

import { mockIonicModal } from './modal';

describe('mockIonicModal', () => {
  it('installs the shared FormModal stub over Ionic Vue', async () => {
    const mocked = await mockIonicModal(() => import('@ionic/vue'));
    expect(mocked.IonModal.name).toBe('IonModal');
    expect(mocked.IonButton).toBeDefined();
  });
});
