// The API's documentation as the page reads it (BASE-G150, G04): the OpenAPI document cut into one section per app, by
// its name, each with its routes in path order — method, path, what it does, its parameters and the schema of its
// body — and the file a person downloads to import it elsewhere (Postman).
import { describe, expect, it } from 'vitest';

import { apiDocFileName, apiDocSections } from './api-docs';

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
        responses: { '200': { description: 'OK' } },
      },
    },
    '/api/cart_checkout/carts/cleanup_expired': {
      post: {
        operationId: 'cart_checkout.cart.cleanup_expired',
        summary: 'Cart Cleanup Expired',
        tags: ['cart_checkout'],
        requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/CleanupIn' } } } },
        responses: { '200': { description: 'OK' } },
      },
    },
    '/api/cart_checkout/carts': {
      get: { operationId: 'cart_checkout.cart.list', summary: 'Cart List', tags: ['cart_checkout'], responses: {} },
    },
  },
  components: { schemas: { CleanupIn: { type: 'object', properties: { days: { type: 'integer' } } } } },
};

const APPS = [
  { id: 'cart_checkout', name: 'Online shop', read: true, write: true },
  { id: 'tax', name: 'Taxes', read: true, write: false },
];

describe('apiDocSections', () => {
  it('one section per app, by name, its routes in path order', () => {
    const sections = apiDocSections(DOCUMENT, APPS);
    expect(sections.map((section) => section.name)).toEqual(['Online shop', 'Taxes']);
    expect(sections[0].routes.map((route) => `${route.method} ${route.path}`)).toEqual([
      'GET /api/cart_checkout/carts',
      'POST /api/cart_checkout/carts/cleanup_expired',
    ]);
  });

  it('each route with what it does, its parameters and the schema of its body', () => {
    const [shop, taxes] = apiDocSections(DOCUMENT, APPS);
    expect(taxes.routes[0]).toMatchObject({
      id: 'tax.category.list',
      summary: 'Category List',
      description: 'Lists the tax categories.',
      parameters: [{ name: 'limit', where: 'query', required: false, type: 'integer', description: 'How many.' }],
      body: null,
    });
    expect(shop.routes[1].body).toEqual({ name: 'CleanupIn', schema: { type: 'object', properties: { days: { type: 'integer' } } } });
  });

  it('an app the document has but the list does not name keeps its id; none: no section', () => {
    expect(apiDocSections(DOCUMENT, [APPS[1]]).map((section) => section.name)).toEqual(['cart_checkout', 'Taxes']);
    expect(apiDocSections({ paths: {} }, APPS)).toEqual([]);
  });
});

describe('apiDocFileName', () => {
  it('names the file after the business', () => {
    expect(apiDocFileName('bar-pepe')).toBe('erplora-bar-pepe-openapi.json');
    expect(apiDocFileName('')).toBe('erplora-openapi.json');
  });
});
