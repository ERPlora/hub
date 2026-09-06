// @vitest-environment happy-dom
// The element a module embeds (hub#1600): defined under its tag, once, without a shadow root — a
// second boot must not throw, and the module's screen must be able to style what is inside.
import { describe, expect, it, vi } from 'vitest';

vi.mock('../components/WhatsAppConnect.vue', () => ({
  default: { name: 'WhatsAppConnect', template: '<p data-test="stub">stub</p>' },
}));

import { WHATSAPP_CONNECT_TAG, registerWhatsAppConnectElement } from './whatsapp-connect';

describe('erp-whatsapp-connect', () => {
  it('is defined once under its tag and survives a second registration', () => {
    registerWhatsAppConnectElement();
    const first = customElements.get(WHATSAPP_CONNECT_TAG);
    expect(first).toBeDefined();
    expect(() => registerWhatsAppConnectElement()).not.toThrow();
    expect(customElements.get(WHATSAPP_CONNECT_TAG)).toBe(first);
  });

  it('renders in the light DOM so the module screen can see and style it', () => {
    registerWhatsAppConnectElement();
    const el = document.createElement(WHATSAPP_CONNECT_TAG);
    document.body.appendChild(el);
    expect(el.shadowRoot).toBeNull();
  });
});
