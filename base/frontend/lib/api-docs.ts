// The API's documentation as the page reads it (BASE-G150, G04): the OpenAPI document of what this business's apps
// publish (`base.api_doc.get`) cut into one section per app, by its name, each with its routes in path order — method,
// path, what it does, its parameters and the schema of its body — and the name of the file a person downloads to
// import it elsewhere (Postman, an integration's own tools).

export interface ApiDocApp {
  id: string;
  name: string;
}

export interface ApiDocParameter {
  name: string;
  where: string;
  required: boolean;
  type: string;
  description: string;
}

export interface ApiDocRoute {
  id: string;
  method: string;
  path: string;
  summary: string;
  description: string;
  parameters: ApiDocParameter[];
  body: { name: string; schema: unknown } | null;
}

export interface ApiDocSection {
  id: string;
  name: string;
  routes: ApiDocRoute[];
}

type Json = Record<string, unknown>;

const METHODS = ['get', 'post', 'put', 'patch', 'delete'];
const REF = '#/components/schemas/';

const asRecord = (value: unknown): Json => (value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Json) : {});
const asText = (value: unknown): string => (typeof value === 'string' ? value : '');

function typeOf(schema: Json): string {
  if (typeof schema.type === 'string') return schema.type;
  const options = Array.isArray(schema.anyOf) ? schema.anyOf.map((option) => asText(asRecord(option).type)).filter(Boolean) : [];
  return options.join(' | ');
}

function bodyOf(route: Json, schemas: Json): ApiDocRoute['body'] {
  const content = asRecord(asRecord(route.requestBody).content);
  const ref = asText(asRecord(asRecord(content['application/json']).schema).$ref);
  if (!ref.startsWith(REF)) return null;
  const name = ref.slice(REF.length);
  return { name, schema: schemas[name] ?? null };
}

/** The document cut into one section per app (by name; an app the list does not name keeps its id). */
export function apiDocSections(document: Json, apps: ApiDocApp[]): ApiDocSection[] {
  const names = new Map(apps.map((app) => [app.id, app.name]));
  const schemas = asRecord(asRecord(document.components).schemas);
  const sections = new Map<string, ApiDocSection>();
  const paths = asRecord(document.paths);
  for (const path of Object.keys(paths).sort()) {
    const item = asRecord(paths[path]);
    for (const method of METHODS) {
      const route = asRecord(item[method]);
      const id = asText(route.operationId);
      if (!id) continue;
      const tags = Array.isArray(route.tags) ? route.tags : [];
      const app = asText(tags[0]) || id.split('.')[0];
      const section = sections.get(app) ?? { id: app, name: names.get(app) ?? app, routes: [] };
      section.routes.push({
        id,
        method: method.toUpperCase(),
        path,
        summary: asText(route.summary),
        description: asText(route.description),
        parameters: (Array.isArray(route.parameters) ? route.parameters : []).map((raw) => {
          const parameter = asRecord(raw);
          return {
            name: asText(parameter.name),
            where: asText(parameter.in),
            required: parameter.required === true,
            type: typeOf(asRecord(parameter.schema)),
            description: asText(parameter.description),
          };
        }),
        body: bodyOf(route, schemas),
      });
      sections.set(app, section);
    }
  }
  return [...sections.values()].sort((a, b) => a.name.localeCompare(b.name));
}

/** The name of the downloaded document: after the business, whose slug names its host. */
export function apiDocFileName(slug: string): string {
  return slug ? `erplora-${slug}-openapi.json` : 'erplora-openapi.json';
}
