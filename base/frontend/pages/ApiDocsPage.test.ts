// The API's documentation (BASE-G150, G04; the old hub's ApiDocsPage, without Swagger UI: production enforces Trusted
// Types): `base.api_doc.get` asked once (the document is far bigger than a live result may be), and only once the live
// `base.api_doc.settings` says it is shown — hidden, nothing is asked, so no refused request reaches the console; one
// section per app with its routes — method, path, what it does — and each route's parameters and body on opening it; how
// to call it (a key from Employees › API keys, as a bearer), said too when this business cannot make keys yet;
// «Download the OpenAPI file». Hidden, it says so, and who runs the business is sent to Settings › General to show it; a
// document that cannot be read says so with «Retry»; none published, says so.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import { saveFile } from '../lib/data';
import ApiDocsPage from './ApiDocsPage.vue';

vi.mock('../lib/data', async (importOriginal) => ({ ...(await importOriginal<typeof import('../lib/data')>()), saveFile: vi.fn() }));

const DOCUMENT = {
  openapi: '3.1.0',
  info: { title: 'ERPlora Hub API', version: '1' },
  paths: {
    '/api/tax/categories': {
      get: {
        operationId: 'tax.category.list',
        summary: 'Category List',
        description: 'Lists the tax categories.',
        tags: ['tax'],
        parameters: [{ in: 'query', name: 'limit', required: false, schema: { type: 'integer' }, description: 'How many.' }],
        responses: {},
      },
    },
  },
  components: { securitySchemes: { ApiKey: { type: 'http', scheme: 'bearer' } } },
};
const ANSWER = { document: DOCUMENT, apps: [{ id: 'tax', name: 'Taxes', read: true, write: false }], keys_available: true };

const SHOWN = { docs_enabled: true, can_change: true };
const HIDDEN = { docs_enabled: false, can_change: true };

/** Opens the page and answers its live `base.api_doc.settings` (`settings`; `'error'` = it cannot be read). */
async function open(
  answer: Response | (() => Response),
  { settings = SHOWN, ...options }: Parameters<typeof mountBase>[1] & { settings?: typeof SHOWN | 'error' } = {},
) {
  const respond = typeof answer === 'function' ? answer : () => answer;
  const m = await mountBase(ApiDocsPage, { path: '/api-docs', routes: ['/api-docs', '/settings'], onApi: respond, ...options });
  const call = await m.live();
  if (settings === 'error') call.push(errorFrame(subId(m.client, 'base.api_doc.settings'), 'internal_error'));
  else await m.result(call, 'base.api_doc.settings', settings);
  await flush();
  return { ...m, call };
}

const refusal = (code: string, status: number) => Response.json({ error: { code, message: 'Server words' } }, { status });

afterEach(() => {
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

describe('ApiDocsPage', () => {
  it('asks for the document once, never live: a section per app with its routes, and how to call it', async () => {
    const m = await open(Response.json(ANSWER), { locale: 'es' });
    expect(m.client.stream.subscriptions('base.api_doc.get')).toHaveLength(0);
    expect(m.wrapper.getComponent(AppPage).props('backHref')).toBe('/settings');
    expect(m.net.api.map((call) => new URL(call.url, 'http://a.localhost').pathname)).toEqual(['/api/api-docs']);
    expect(m.wrapper.text()).toContain('Documentación de la API');
    expect(m.wrapper.text()).toContain('Empleados › API keys');
    expect(m.wrapper.find('[data-testid="api-docs-section"] h2').text()).toBe('Taxes');
    const route = m.wrapper.get('[data-testid="api-docs-route"]');
    expect(route.text()).toContain('GET');
    expect(route.text()).toContain('/api/tax/categories');
    expect(route.text()).toContain('Lists the tax categories.');
    expect(route.text()).toContain('limit');
    expect(m.wrapper.find('[data-testid="api-docs-keys-soon"]').exists()).toBe(false);
  });

  it('says when this business cannot make keys yet', async () => {
    const m = await open(Response.json({ ...ANSWER, keys_available: false }));
    expect(m.wrapper.get('[data-testid="api-docs-keys-soon"]').text()).toContain('API keys are not available yet for this business');
  });

  it('«Download the OpenAPI file» saves the document', async () => {
    const m = await open(Response.json(ANSWER));
    await m.wrapper.get('[data-testid="api-docs-download"]').trigger('click');
    const [name, blob] = vi.mocked(saveFile).mock.calls[0];
    expect(name).toMatch(/^erplora-.*openapi\.json$/);
    expect(JSON.parse(await (blob as Blob).text())).toEqual(DOCUMENT);
  });

  it('hidden, it says so without asking for the document; who runs the business is sent to Settings › General', async () => {
    const m = await open(() => refusal('base.api_docs_hidden', 409), { settings: HIDDEN });
    expect(m.net.api).toHaveLength(0);
    expect(m.wrapper.text()).toContain('The API documentation is hidden in this business.');
    expect(m.wrapper.get('[data-testid="api-docs-show"]').attributes('href')).toBe('/settings');
    const other = await open(() => refusal('base.api_docs_hidden', 409), { settings: HIDDEN, session: EMPLOYEE });
    expect(other.net.api).toHaveLength(0);
    expect(other.wrapper.find('[data-testid="api-docs-show"]').exists()).toBe(false);
  });

  it('hidden between the settings and the document, the server’s refusal says it is hidden too', async () => {
    const m = await open(() => refusal('base.api_docs_hidden', 409));
    expect(m.wrapper.text()).toContain('The API documentation is hidden in this business.');
  });

  it('shown or hidden again while the page is kept open, it asks for the document only when shown', async () => {
    const m = await open(() => Response.json(ANSWER), { settings: HIDDEN });
    expect(m.client.stream.subscriptions('base.api_doc.settings').map((sub) => sub.params)).toEqual([{}]);
    expect(m.net.api).toHaveLength(0);
    await m.result(m.call, 'base.api_doc.settings', SHOWN, 2);
    await flush();
    expect(m.net.api).toHaveLength(1);
    expect(m.wrapper.find('[data-testid="api-docs-section"]').exists()).toBe(true);
    await m.result(m.call, 'base.api_doc.settings', HIDDEN, 3);
    await flush();
    expect(m.net.api).toHaveLength(1);
    expect(m.wrapper.text()).toContain('The API documentation is hidden in this business.');
    expect(m.wrapper.find('[data-testid="api-docs-section"]').exists()).toBe(false);
  });

  it('settings that cannot be read do not keep the document away: it is asked for all the same', async () => {
    const m = await open(Response.json(ANSWER), { settings: 'error' });
    expect(m.net.api).toHaveLength(1);
    expect(m.wrapper.find('[data-testid="api-docs-section"]').exists()).toBe(true);
  });

  it('a document that cannot be read says so; «Retry» asks again', async () => {
    let failing = true;
    const m = await open(() => (failing ? refusal('internal_error', 500) : Response.json(ANSWER)));
    expect(m.wrapper.text()).toContain('Could not load the documentation.');
    failing = false;
    await m.wrapper.get('[data-testid="api-docs-retry"]').trigger('click');
    await flush();
    expect(m.wrapper.find('[data-testid="api-docs-section"]').exists()).toBe(true);
  });

  it('none published, says so', async () => {
    const m = await open(Response.json({ ...ANSWER, document: { paths: {} }, apps: [] }));
    expect(m.wrapper.text()).toContain('None of this business’s apps publishes its API yet.');
  });
});
