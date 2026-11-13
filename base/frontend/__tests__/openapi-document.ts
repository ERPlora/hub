// Pieces of the hub's OpenAPI document (`/api/openapi.json`) for the tests of the API docs: one fixture, so the
// documented operation every test opens with reads the same in the page's test and the helper's.

/** The document's version and title. */
export const OPENAPI_HEAD = { openapi: '3.1.0', info: { title: 'ERPlora Hub API', version: '1' } };

/** The tax categories' list as the hub documents it, its responses aside. */
export const TAX_CATEGORY_LIST = {
  operationId: 'tax.category.list',
  summary: 'Category List',
  description: 'Lists the tax categories.',
  tags: ['tax'],
  parameters: [{ in: 'query', name: 'limit', required: false, schema: { type: 'integer' }, description: 'How many.' }],
};
