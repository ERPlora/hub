// Documentación de la API pública del Hub (ADR-0057 §4, refinado 2026-06-24).
//
// La doc Swagger se renderiza en una VISTA Vue interna del Hub (ApiDocsPage.vue), no en una URL
// pública: `swagger-ui-dist` (npm) recibe el spec por la opción `spec:`, así que Swagger NUNCA hace
// su propio fetch sin auth. El spec (`GET /api/v1/openapi.json`) es interno y exige sesión de
// usuario: aquí lo pedimos con el MISMO fetch autenticado del resto de `/api/*` (runtimeHeaders →
// X-Hub-Session). Visible para cualquier usuario logueado (verla es inofensivo; usar la API exige
// una API key con permiso, no la sesión).
//
// Toggle "Mostrar documentación de la API": ahora es un SETTING DEL HUB server-side (hub-settings.ts
// → `api_docs_enabled` de /api/settings), no una preferencia local. Solo lo cambia un admin (PUT
// /api/settings revalida owner/admin); el valor es compartido por todo el hub. Controla la
// visibilidad de la entrada de menú (App.vue) y el gate de la ruta (router). La seguridad real sigue
// siendo el gate de SESIÓN sobre `openapi.json` en el runtime (defensa real, no este flag).

import { computed } from 'vue';
import { RUNTIME_URL, runtimeHeaders } from './runtime';
import { hubSettings } from './hub-settings';

/**
 * ¿Está visible la documentación de la API? Deriva del setting server-side del hub
 * (`api_docs_enabled`). `null` (settings aún sin cargar) → OFF, por defecto seguro.
 */
export const apiDocsEnabled = computed<boolean>(() => hubSettings.value?.api_docs_enabled === true);

/** Spec OpenAPI 3.1 (forma libre; se lo pasamos tal cual a Swagger por `spec:`). */
export type OpenApiSpec = Record<string, unknown>;

/**
 * Descarga el spec OpenAPI del runtime con el fetch AUTENTICADO del web app (X-Hub-Session). El
 * runtime exige sesión de usuario (401 si anónimo o si llega con bearer de API key). Lanza si falla;
 * la vista lo muestra como estado de error en vez de un Swagger roto.
 */
export async function fetchOpenApiSpec(): Promise<OpenApiSpec> {
  const res = await fetch(`${RUNTIME_URL}/api/v1/openapi.json`, { headers: runtimeHeaders() });
  if (!res.ok) throw new Error(`openapi.json → ${res.status}`);
  return (await res.json()) as OpenApiSpec;
}
