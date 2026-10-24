// The API's documentation (BASE-G150, G04; the old hub's ApiDocsPage, without Swagger UI: production enforces Trusted
// Types): `base.api_doc.get` asked once (the document is far bigger than a live result may be), one section per app with its routes — method, path, what it does — and each route's
// parameters and body on opening it; how to call it (a key from Employees › API keys, as a bearer), said too when this
// business cannot make keys yet; «Download the OpenAPI file». Hidden, it says so, and who runs the business is sent to
// Settings › General to show it; a document that cannot be read says so with «Retry»; none published, says so.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, flush, mountBase } from '../__tests__/mount-base';
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

async function open(answer: Response | (() => Response), options: Parameters<typeof mountBase>[1] = {}) {
  const respond = typeof answer === 'function' ? answer : () => answer;
  const m = await mountBase(ApiDocsPage, { path: '/api-docs', routes: ['/api-docs', '/settings'], onApi: respond, ...options });
  await flush();
  return m;
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

  it('hidden, it says so; who runs the business is sent to Settings › General', async () => {
    const m = await open(() => refusal('base.api_docs_hidden', 409));
    expect(m.wrapper.text()).toContain('The API documentation is hidden in this business.');
    expect(m.wrapper.get('[data-testid="api-docs-show"]').attributes('href')).toBe('/settings');
    const other = await open(() => refusal('base.api_docs_hidden', 409), { session: EMPLOYEE });
    expect(other.wrapper.find('[data-testid="api-docs-show"]').exists()).toBe(false);
  });

  it('shown or hidden again while the page is kept open, it asks for the document again', async () => {
    let hiddenNow = true;
    const m = await open(() => (hiddenNow ? refusal('base.api_docs_hidden', 409) : Response.json(ANSWER)));
    const call = await m.live();
    expect(m.client.stream.subscriptions('base.api_doc.settings').map((sub) => sub.params)).toEqual([{}]);
    await m.result(call, 'base.api_doc.settings', { docs_enabled: false, can_change: true });
    hiddenNow = false;
    await m.result(call, 'base.api_doc.settings', { docs_enabled: true, can_change: true }, 2);
    await flush();
    expect(m.net.api).toHaveLength(2);
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
