// Settings del Hub (key/value server-side). Cliente del store de ajustes que vive en el runtime.
//
// Contrato (decisión del humano):
//   - GET /api/settings → { currency, language, api_docs_enabled }   (auth = sesión)
//   - PUT /api/settings { ...parcial } → objeto COMPLETO              (auth = owner/admin)
//
// Estos ajustes son del HUB (globales), no del usuario. La MONEDA es global (sin override por
// usuario). El IDIOMA es el DEFAULT del hub; cada usuario puede tener su propio override local
// (localStorage `erplora.locale`, ver i18n/index.ts) que prevalece — la reconciliación la hace
// `bootHubLanguage()` más abajo.
//
// Se llama con el MISMO fetch autenticado del resto de `/api/*` (runtimeHeaders → X-Hub-Session):
// el GET solo exige sesión; el PUT lo revalida el runtime contra owner/admin (la UI gatea con
// `isAdmin` solo para mostrar/ocultar, la autoridad es el runtime).
import { ref } from 'vue';
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Forma del store de settings del hub. Todos los campos llegan siempre en el GET/PUT completos. */
export interface HubSettings {
  /** Moneda ISO-4217 del hub (global, sin override por usuario). Default servidor: EUR. */
  currency: string;
  /** Idioma DEFAULT del hub (código de locale, p.ej. 'es' | 'en'). El usuario puede overridearlo. */
  language: string;
  /** ¿Está visible la documentación de la API (entrada de menú + página Swagger)? */
  api_docs_enabled: boolean;
  /** Identidad de NEGOCIO (FUENTE ÚNICA país-agnóstica, ADR-0061): identificador fiscal universal
   *  (NIF/CIF en ES, SIREN/SIRET en FR, VAT-ID…) del obligado tributario. La usan invoice (emisor),
   *  los módulos fiscales por país (verifactu…) y los documentos de venta. Vacío hasta configurarse. */
  business_tax_id: string;
  /** Razón social / nombre legal del negocio. */
  business_legal_name: string;
  /** Dirección fiscal (texto libre, una o varias líneas). */
  business_address: string;
}

/**
 * Cache reactiva de los settings del hub, resuelta en el boot. Es la fuente de la moneda del hub
 * (money.ts), del idioma DEFAULT (i18n) y del toggle de doc de la API (api-docs.ts / nav / router).
 * `null` hasta el primer fetch: los consumidores degradan con sus defaults (EUR / 'es' / OFF).
 */
export const hubSettings = ref<HubSettings | null>(null);

/** Aplica una respuesta del runtime a la cache reactiva, normalizando tipos defensivamente. */
function setHubSettings(raw: unknown): HubSettings {
  const r = (raw ?? {}) as Partial<HubSettings>;
  const next: HubSettings = {
    currency: typeof r.currency === 'string' && r.currency.trim() ? r.currency.trim().toUpperCase() : 'EUR',
    language: typeof r.language === 'string' && r.language.trim() ? r.language.trim() : 'es',
    api_docs_enabled: r.api_docs_enabled === true,
    business_tax_id: typeof r.business_tax_id === 'string' ? r.business_tax_id : '',
    business_legal_name: typeof r.business_legal_name === 'string' ? r.business_legal_name : '',
    business_address: typeof r.business_address === 'string' ? r.business_address : '',
  };
  hubSettings.value = next;
  return next;
}

/** Lee los settings del hub (`GET /api/settings`). Exige sesión. Lanza si el runtime falla. */
export async function getHubSettings(): Promise<HubSettings> {
  const res = await fetch(`${RUNTIME_URL}/api/settings`, { headers: runtimeHeaders() });
  if (!res.ok) throw new Error(`settings → ${res.status}`);
  return setHubSettings(await res.json());
}

/**
 * Actualiza (parcial) los settings del hub (`PUT /api/settings`). El runtime exige owner/admin y
 * devuelve el objeto COMPLETO, que cacheamos. Lanza si falla (403 si no es admin, etc.).
 */
export async function updateHubSettings(partial: Partial<HubSettings>): Promise<HubSettings> {
  const res = await fetch(`${RUNTIME_URL}/api/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
    body: JSON.stringify(partial),
  });
  if (!res.ok) throw new Error(`settings PUT → ${res.status}`);
  return setHubSettings(await res.json());
}
