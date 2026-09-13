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
  /**
   * Dirección fiscal en UNA línea. Desde hub#1846 la COMPONE el runtime a partir de las partes de
   * abajo; se lee (la imprimen facturas y tiques) y ya no se escribe desde aquí.
   */
  business_address: string;
  /** Vía pública del domicilio fiscal (hub#1846). */
  business_street: string;
  /** Número. Puede faltar de verdad (un «s/n»). */
  business_street_number: string;
  /** Código postal. */
  business_postal_code: string;
  /** Municipio. */
  business_city: string;
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
  /** **NO es un ajuste: es el parte del último `PUT`** (hub#1306). Guardar la identidad de negocio
   *  la PUBLICA en el SaaS —es lo que le permite nombrar al obligado en el otorgamiento del Anexo
   *  I—, y esa publicación es best-effort: los ajustes ya están escritos, así que un SaaS caído no
   *  puede costarle el guardado al cliente. El runtime contesta `200` y entrega el fallo como
   *  código ESTABLE (`cloud_rejected`, `cloud_unreachable`) en esta clave. Ausente = no hubo nada
   *  que contar. Vive con la respuesta, no con el hub: cada `GET`/`PUT` la reescribe. */
  fiscal_identity_publish_error?: string;
}

/**
 * Cache reactiva de los settings del hub, resuelta en el boot. Es la fuente de la moneda del hub
 * (money.ts), del idioma DEFAULT (i18n) y del toggle de doc de la API (api-docs.ts / nav / router).
 * `null` hasta el primer fetch: los consumidores degradan con sus defaults (EUR / 'es' / OFF).
 */
export const hubSettings = ref<HubSettings | null>(null);

/**
 * La zona horaria IANA del NEGOCIO, ya RESUELTA (hub#731, hub#1022) — NO la clave cruda de
 * `HubSettings.timezone` (que es `null` mientras se deduce del país y tiene que poder volver por
 * un `PUT`): esta es la que el runtime entrega en `/api/hub/context` (`timezone_name()`), siempre
 * un nombre válido. La siembra `bootHubContext` vía `publishHubTimezone`; se refresca en el
 * siguiente boot (cambiar país/zona en Ajustes no la re-resuelve en caliente — igual que la
 * deducción, es una decisión de dueño que vive con la sesión).
 *
 * Es el espejo de `lib/money.ts → hubCurrency()`: una fuente, publicada como dato global para que
 * el `@erplora/module-sdk` (`erplora.timezone`) y el shell lean el MISMO reloj que el runtime le
 * entrega a los handlers como `context.timezone` / `:timezone`.
 */
export function hubTimezone(): string {
  return publishedHubTimezone() ?? 'UTC';
}

/**
 * La zona ya PUBLICADA, o `null` si el boot todavía no la ha sembrado (hub#1212).
 *
 * Es la misma lectura que `hubTimezone()` sin su degradación, y existe porque `UTC` y «aún no lo
 * sé» son dos respuestas distintas que `hubTimezone()` no puede separar. Quien pinta fechas
 * (`lib/format-datetime.ts`) necesita distinguirlas: antes del boot, `UTC` sería una hora mal en
 * España diez meses al año, así que ahí cae al huso del navegador —lo que ya se veía— en vez de
 * afirmar un reloj que nadie ha dicho. El contrato de `hubTimezone()` no cambia: el SDK de los
 * módulos sigue leyendo `UTC` como último recurso.
 */
export function publishedHubTimezone(): string | null {
  const published = (globalThis as { __erploraTimezone?: string }).__erploraTimezone;
  return typeof published === 'string' && published.trim() ? published.trim() : null;
}

/**
 * Publica la zona horaria RESUELTA del negocio en `globalThis.__erploraTimezone` (hub#1022), de
 * donde la leen `hubTimezone()` y el SDK de los módulos. Mirror de `publishHubCurrency`: la zona
 * del negocio es global (no hay override por usuario). Recibe el valor RESUELTO — si un caller le
 * pasa el setting crudo `null`, degrada a `UTC` en vez de publicar «no lo sé».
 */
export function publishHubTimezone(timezone: string | null | undefined): void {
  try {
    (globalThis as { __erploraTimezone?: string }).__erploraTimezone =
      typeof timezone === 'string' && timezone.trim() ? timezone.trim() : 'UTC';
  } catch {
    /* noop — degradación elegante */
  }
}

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
    business_street: typeof r.business_street === 'string' ? r.business_street : '',
    business_street_number: typeof r.business_street_number === 'string' ? r.business_street_number : '',
    business_postal_code: typeof r.business_postal_code === 'string' ? r.business_postal_code : '',
    business_city: typeof r.business_city === 'string' ? r.business_city : '',
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
    pin_length: r.pin_length === 4 || r.pin_length === 6 ? r.pin_length : 4,
  };
  // El parte de la publicación de la identidad fiscal (hub#1306) viaja CON la respuesta, no con el
  // hub: se copia tal cual cuando viene y se deja fuera cuando no, para que un veredicto viejo no
  // haga avisar de un guardado que sí publicó.
  if (typeof r.fiscal_identity_publish_error === 'string' && r.fiscal_identity_publish_error.trim()) {
    next.fiscal_identity_publish_error = r.fiscal_identity_publish_error.trim();
  }
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
 * The runtime refusal, as the runtime wrote it (hub#684).
 *
 * `PUT /api/settings` answers `{error:{code,message}}` and that `message` is written to be read (e.g.
 * the frozen tax id names the id and the date it froze). It used to be thrown away and the screen
 * painted a flat «could not save settings»: the only explanation the product had reached nobody.
 */
export class HubSettingsError extends Error {
  /** Stable runtime code (`business_tax_id_frozen`, `hub_country_frozen`…). */
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
 * admin, 409 si el congelado del NIF o del país se niegan…).
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
