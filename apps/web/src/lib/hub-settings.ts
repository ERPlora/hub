// Settings del Hub (key/value server-side). Cliente del store de ajustes que vive en el runtime.
//
// Contrato (decisión del humano):
//   - GET /api/settings → { currency, language, api_docs_enabled }   (auth = sesión)
//   - PUT /api/settings { ...parcial } → objeto COMPLETO              (auth = owner/admin)
//
// Estos ajustes son del HUB (globales), no del usuario. La MONEDA es global (sin override por
// usuario). El IDIOMA es el DEFAULT del hub; cada usuario puede tener su propio override persistido
// (`hub_user_pref`, ver user-profile.ts) que prevalece — la reconciliación la hace
// `bootHubLanguage()` más abajo.
//
// Se llama con el MISMO fetch autenticado del resto de `/api/*` (runtimeHeaders → X-Hub-Session):
// el GET solo exige sesión; el PUT lo revalida el runtime contra owner/admin (la UI gatea con
// `isAdmin` solo para mostrar/ocultar, la autoridad es el runtime).
import { ref } from 'vue';
import { publishPinPolicy, type PinPolicy } from './pin-policy';
import { RUNTIME_URL, runtimeHeaders } from './runtime';
import { setHubPalette } from './theme';

/** Forma del store de settings del hub. Todos los campos llegan siempre en el GET/PUT completos. */
export interface HubSettings {
  /** Moneda ISO-4217 del hub (global, sin override por usuario). Default servidor: EUR. */
  currency: string;
  /** Los DECIMALES de la moneda (ADR-0123 §7): EUR 2, **JPY 0**, KWD 3. La escala del dinero, que
   *  NO se puede asumir 2. Lo resuelve el runtime (`/api/hub/context`) del registro ISO-4217, o de
   *  lo que el hub haya declarado a mano si su moneda no está en él. */
  currency_decimals?: number;
  /** Idioma DEFAULT del hub (código de locale, p.ej. 'es' | 'en'). El usuario puede overridearlo. */
  language: string;
  /** ¿Está visible la documentación de la API (entrada de menú + página Swagger)? */
  api_docs_enabled: boolean;
  /** País fiscal ISO-3166-1 alpha-2. Driver global para impuestos/compliance. */
  country_code: string;
  /** Subdivisión fiscal ISO-3166-2, o null si aplica el régimen general del país. */
  region_code?: string | null;
  /** Zona horaria IANA del NEGOCIO (hub#731), o null = «dedúcela de `country_code`/`region_code`»,
   *  que es el caso normal. Es el reloj con el que el kernel de flujos lee un trigger `cron`:
   *  «cierra la caja a las 21:00» son las 21:00 de la tienda, no UTC. Solo hace falta declararla
   *  en un país con varios husos. Las `scheduled_tasks` de los módulos NO la usan: son UTC. */
  timezone?: string | null;
  /** Identidad de NEGOCIO (FUENTE ÚNICA país-agnóstica, ADR-0061): identificador fiscal universal
   *  (NIF/CIF en ES, SIREN/SIRET en FR, VAT-ID…) del obligado tributario. La usan invoice (emisor),
   *  los módulos fiscales por país (verifactu…) y los documentos de venta. Vacío hasta configurarse. */
  business_tax_id: string;
  /** Razón social / nombre legal del negocio. */
  business_legal_name: string;
  /** Dirección fiscal (texto libre, una o varias líneas). */
  business_address: string;
  /** Paleta de tema GLOBAL del hub (ADR-0138): valor de `data-ok-palette` de OutfitKit
   *  palettes.css; 'erplora' = marca por defecto. El override POR USUARIO vive en
   *  `hub_user_pref` y gana a esta. */
  theme_palette: string;
  /** Cada cuánto pregunta el hub QUIÉN está en la caja (hub#359). `never` = no se pregunta y las
   *  ventas dejan de llevar el nombre de quien las hizo. Se compone con el modo del DISPOSITIVO
   *  (hub#358) por el lado restrictivo, y esa composición la hace el runtime, no el navegador. */
  pin_policy: PinPolicy;
  /** Minutos de INACTIVIDAD antes de que el shell cierre la sesión y vuelva al pinpad (hub#628).
   *  Solo tiene efecto con `pin_policy = always` y en dispositivos `shared`; quien lo aplica es
   *  el detector del shell (lib/idle-logout), el TTL de servidor queda como red. */
  pin_inactivity_minutes: number;
  /** Cuántos DÍGITOS tiene el PIN de este hub (hub#974): 4 o 6, igual para todo el mundo. Fija a
   *  propósito — es lo que permite que el teclado envíe al último dígito en vez de pedir un
   *  «Aceptar» que el cajero pulsaría decenas de veces al día. Lo normaliza `lib/pin-length`. */
  pin_length: number;
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
    country_code:
      typeof r.country_code === 'string' && r.country_code.trim()
        ? r.country_code.trim().toUpperCase()
        : 'ES',
    region_code:
      typeof r.region_code === 'string' && r.region_code.trim()
        ? r.region_code.trim().toUpperCase()
        : null,
    // Nombre IANA tal cual (`Europe/Madrid`): NO se pone en mayúsculas — el runtime valida contra
    // la tzdb y `EUROPE/MADRID` no existe. `null` = la deduce el hub del país.
    timezone: typeof r.timezone === 'string' && r.timezone.trim() ? r.timezone.trim() : null,
    business_tax_id: typeof r.business_tax_id === 'string' ? r.business_tax_id : '',
    business_legal_name: typeof r.business_legal_name === 'string' ? r.business_legal_name : '',
    business_address: typeof r.business_address === 'string' ? r.business_address : '',
    theme_palette: typeof r.theme_palette === 'string' && r.theme_palette.trim() ? r.theme_palette.trim() : 'erplora',
    // El dial «pedir PIN» (hub#359). Lo normaliza `publishPinPolicy` —cerrado, sin trim ni
    // minúsculas— porque lo que NO se puede leer no puede degradar a `never`: esa es la posición
    // que deja de atribuir las ventas a una persona.
    pin_policy: publishPinPolicy(r.pin_policy),
    // Minutos de inactividad del pinpad (hub#628). Espejo del runtime: un valor ilegible o fuera
    // de rango degrada al DEFAULT (5), nunca a un borde.
    pin_inactivity_minutes:
      Number.isInteger(r.pin_inactivity_minutes) &&
      (r.pin_inactivity_minutes as number) >= 1 &&
      (r.pin_inactivity_minutes as number) <= 30
        ? (r.pin_inactivity_minutes as number)
        : 5,
    // Longitud del PIN (hub#974). Un valor que no sea 4 ni 6 degrada al default (6): pintar un
    // teclado con una longitud que el runtime va a rechazar sería fallar en caja, con cola.
    pin_length: r.pin_length === 4 || r.pin_length === 6 ? r.pin_length : 6,
  };
  hubSettings.value = next;
  // La paleta global se refleja en el shell al momento (theme.ts decide si hay override local).
  setHubPalette(next.theme_palette);
  return next;
}

/** Lee los settings del hub (`GET /api/settings`). Exige sesión. Lanza si el runtime falla. */
export async function getHubSettings(): Promise<HubSettings> {
  const res = await fetch(`${RUNTIME_URL}/api/settings`, { headers: runtimeHeaders() });
  if (!res.ok) throw new Error(`settings → ${res.status}`);
  return setHubSettings(await res.json());
}

/**
 * El rechazo del runtime, tal y como lo escribió (hub#684).
 *
 * `PUT /api/settings` contesta `{error:{code,message}}` y ese `message` está redactado para leerlo
 * —el de la demo es *«this is a demo hub: its tax id and legal name are read-only — to issue real
 * invoices, create your own hub»*—. Antes se tiraba entero y la pantalla pintaba un «no se pudieron
 * guardar los ajustes» plano: la única explicación que el producto tenía no llegaba a nadie.
 */
export class HubSettingsError extends Error {
  /** Código estable del runtime (`demo_fiscal_identity_locked`, `business_tax_id_frozen`…). */
  readonly code: string;
  /** Estado HTTP, para quien necesite distinguir un 409 de un 403 sin mirar el código. */
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = 'HubSettingsError';
    this.code = code;
    this.status = status;
  }
}

/**
 * Actualiza (parcial) los settings del hub (`PUT /api/settings`). El runtime exige owner/admin y
 * devuelve el objeto COMPLETO, que cacheamos. Lanza [`HubSettingsError`] si falla (403 si no es
 * admin, 409 si el cierre de la demo o el congelado del NIF se niegan…).
 */
export async function updateHubSettings(partial: Partial<HubSettings>): Promise<HubSettings> {
  const res = await fetch(`${RUNTIME_URL}/api/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
    body: JSON.stringify(partial),
  });
  if (!res.ok) {
    // Un cuerpo ilegible NO se convierte en un mensaje vacío: degrada a la línea de estado, que al
    // menos dice que algo pasó. Un toast en blanco se lee como «no ha pasado nada».
    const body = (await res.json().catch(() => null)) as
      | { error?: { code?: string; message?: string } | string }
      | null;
    const error = typeof body?.error === 'object' ? body?.error : undefined;
    throw new HubSettingsError(
      error?.message || `settings PUT → ${res.status}`,
      error?.code || (typeof body?.error === 'string' ? body.error : 'settings_save_failed'),
      res.status,
    );
  }
  return setHubSettings(await res.json());
}
