// flow: FLOW-F10
// «Choose what happens» reads one phrase per event, in English and in Spanish, never the words the editor composes for
// an event nobody wrote down («WhatsApp inbox: channel connected», «Bandeja de WhatsApp: template alta»); what only the
// platform records (the clean-up of old prints, what a recovery from a separate copy brings back) is not offered. The
// owner of hub `a` opens the editor of a new automation at each size and in each language and reads the whole list;
// nothing is saved. Each size and language leaves its capture of the list searched by «WhatsApp».
import { type Browser, expect, type Page, test } from '@playwright/test';

import { choose } from './flow-helpers';
import { A, capture, horizontalOverflow, login, shown } from './helpers';

const KEY = 'FIX-HUB-FLOW-TRIGGER-LIST-READS-A-PHRASE';
const SIZES = [
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
];
const LANGUAGES = [
  {
    code: 'en',
    somethingHappens: 'Something happens',
    phrases: {
      'whatsapp_inbox.channel.connected': 'the WhatsApp number is connected',
      'whatsapp_inbox.template.created': 'a WhatsApp template is created',
      'printing.device.registered': 'a device is set up to print',
      'website.site.published': 'the website is published',
    },
  },
  {
    code: 'es',
    somethingHappens: 'Pasa algo',
    phrases: {
      'whatsapp_inbox.channel.connected': 'se conecta el número de WhatsApp',
      'whatsapp_inbox.template.created': 'se crea una plantilla de WhatsApp',
      'printing.device.registered': 'se prepara un dispositivo para imprimir',
      'website.site.published': 'se publica la página web',
    },
  },
];
const SYSTEM_ONLY = ['printing.job.pruned', 'customer.customer.restored', 'appointment.appointment.restored'];
const OPTION = '[data-testid^=flow-trigger-event-option-]';

/** Each option of the open list: its event and the words it is read by, without the grey line under them. */
function listed(page: Page): Promise<Array<{ event: string; words: string }>> {
  return page.locator(OPTION).evaluateAll((options) =>
    options.map((option) => {
      const label = option.querySelector('ion-label');
      const own = [...(label?.childNodes ?? [])].filter((node) => node.nodeType === Node.TEXT_NODE);
      return {
        event: (option.getAttribute('data-testid') ?? '').replace('flow-trigger-event-option-', ''),
        words: own.map((node) => node.textContent ?? '').join('').trim(),
      };
    }),
  );
}

async function inEditor(browser: Browser, size: (typeof SIZES)[number], code: string, steps: (page: Page) => Promise<void>) {
  const context = await browser.newContext({ viewport: size });
  const page = await context.newPage();
  try {
    await login(page, A, '/');
    await context.addCookies([{ name: 'django_language', value: code, domain: new URL(A).hostname, path: '/' }]);
    await page.goto(`${A}/flow/automations/new`);
    await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${code}`));
    await expect(shown(page).locator('[data-testid=flow-editor-nosteps]')).toBeVisible();
    // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    await steps(page);
  } finally {
    await context.close();
  }
}

for (const size of SIZES) {
  for (const language of LANGUAGES) {
    test(`FLOW-F10: «Choose what happens» reads a phrase per event in ${language.code} at ${size.label}`, async ({ browser }) => {
      await inEditor(browser, size, language.code, async (page) => {
        await shown(page).locator('[data-testid=flow-trigger-open]').click();
        await choose(page, 'flow-trigger-kind', language.somethingHappens);
        const input = shown(page).locator('[data-testid=flow-trigger-event] input');
        await input.click();
        await expect(page.locator(OPTION).first()).toBeVisible();

        const options = await listed(page);
        const byEvent = Object.fromEntries(options.map(({ event, words }) => [event, words]));
        for (const [event, words] of Object.entries(language.phrases)) expect(byEvent[event], event).toBe(words);
        expect(options.filter(({ words }) => words.includes(': ')), 'composed from internal words').toEqual([]);
        expect(options.filter(({ event }) => SYSTEM_ONLY.includes(event)), 'only the platform records it').toEqual([]);

        await input.fill('WhatsApp');
        await expect(page.locator(`[data-testid="flow-trigger-event-option-whatsapp_inbox.channel.connected"]`)).toBeVisible();
        expect(await horizontalOverflow(page), 'no sideways scroll').toBeLessThanOrEqual(0);
        await capture(page, `${KEY}-${language.code}-${size.label}`);
      });
    });
  }
}
