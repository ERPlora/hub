// hub#2342 — the unknown-outcome verdict must not talk about charges when nothing was charged.
//
// hub#906 gave every command the hub never answered one honest sentence. It carried a tail for the
// incident that motivated it (a double charge): «if it was a charge, check Sales before charging
// again». But the same sentence is the verdict of EVERY command — saving a flow, a WhatsApp
// template, uploading the certificate, retrying a print, adding a customer — and since hub#2320 of
// the core REST writes too. There the tail about charges and Sales misleads whoever reads it.
//
// The charge guidance lives where the charge happens: the POS of `sales` already renders its own
// «we can't tell whether it charged» panel with a link to Sales (sales#91), as Square/Shopify POS
// only warn about a possible duplicate charge inside the payment flow. The kernel's net says only
// what is true for any command.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ErploraClient, HttpWsTransport, commandVerdictMessage, type Notification } from './index.ts';

const webkitDeadFetch = (async () => {
  throw new TypeError('Load failed');
}) as unknown as typeof fetch;

const CHARGE_WORDS = /cobr|venta|charg|sales/i;

for (const locale of ['es', 'en']) {
  test(`hub#2342: the verdict (${locale}) says only what holds for any command — no charge/Sales tail`, () => {
    const msg = commandVerdictMessage(locale);
    assert.doesNotMatch(msg, CHARGE_WORDS, `charge guidance leaked into the generic verdict: ${msg}`);
    // The honest part stays: the outcome is unknown and it must be checked before retrying.
    if (locale === 'es') {
      assert.equal(msg, 'No sabemos si la operación se completó. Comprueba el resultado antes de reintentar.');
    } else {
      assert.equal(msg, "We can't tell whether the operation completed. Check the result before trying again.");
    }
  });
}

test('hub#2342: saving a flow with the hub unreachable toasts the generic verdict, nothing about charges', async () => {
  const notes: Notification[] = [];
  const client = new ErploraClient(new HttpWsTransport({ baseUrl: 'http://h', fetchImpl: webkitDeadFetch }), {
    notifier: (n) => notes.push(n),
  });
  await assert.rejects(
    () => client.command('flows.save_flow', { name: 'Restock' }),
    (e: unknown) => {
      assert.doesNotMatch((e as Error).message, CHARGE_WORDS);
      return true;
    },
  );
  assert.equal(notes.length, 1);
  assert.doesNotMatch(notes[0]!.message, CHARGE_WORDS, `toast talks about charges: ${notes[0]!.message}`);
});
