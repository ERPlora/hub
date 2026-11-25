// The IRPF withholding in «New manual invoice» (INVOICE-F03): none unless one is chosen, never on a ticket.
import { describe, expect, it } from 'vitest';

import { CREATED, setup } from '../__tests__/invoice-create';
import { click, ionValue } from '../__tests__/mount-invoice';

describe('InvoiceCreateModal: the IRPF withholding', () => {
  type Select = HTMLElement & { value: unknown; errorText?: string };
  async function invoiceReady() {
    const s = await setup();
    await s.choose('FACT', 'F1');
    await s.recipient();
    await s.line('Course', '100');
    const withholding = () => s.inDoc('invoice-create-withholding') as Select | null;
    /** What the window sends. */
    async function sent() {
      s.answer(201, CREATED);
      await click(s.submit());
      return s.sent().at(-1)?.body as { withholding_rate?: number };
    }
    return { ...s, withholding, sent };
  }

  it('starts without one, and the server is not told', async () => {
    const s = await invoiceReady();
    expect(s.withholding()?.value).toBe(0);
    expect(await s.sent()).not.toHaveProperty('withholding_rate');
  });

  it('sends the rate chosen', async () => {
    const s = await invoiceReady();
    await ionValue(s.withholding(), 15);
    expect((await s.sent()).withholding_rate).toBe(15);
  });

  it('a ticket is not asked for it, nor keeps the one chosen before', async () => {
    const s = await invoiceReady();
    await ionValue(s.withholding(), 7);
    await s.choose('TICKET', 'F2');
    expect(s.withholding()).toBeNull();
    expect(await s.sent()).not.toHaveProperty('withholding_rate');
  });

  it('a refusal goes under it', async () => {
    const s = await invoiceReady();
    await ionValue(s.withholding(), 15);
    s.answer(409, { error: { code: 'invoice.withholding_on_ticket', message: 'Refused.', fields: { withholding_rate: 'A ticket carries none.' } } });
    await click(s.submit());
    expect(s.withholding()?.errorText).toBe('A ticket carries none.');
  });

  it('opened again, starts without one', async () => {
    const s = await invoiceReady();
    await ionValue(s.withholding(), 15);
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    expect(s.withholding()?.value).toBe(0);
  });

  it('Android Back asks once a rate is chosen, and no more once there is none', async () => {
    const s = await setup();
    await s.territory('vat', '21.00');
    const withhold = (rate: number) => ionValue(s.inDoc('invoice-create-withholding'), rate);
    await s.asksBeforeClosing(() => withhold(15), () => withhold(0));
  });
});
