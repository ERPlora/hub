/** Navegación secundaria real de Ajustes. `store` se retiró porque duplicaba datos de Hub. */
export const SETTINGS_TABS = ['hub', 'business', 'tickets', 'permissions', 'data'] as const;

export type SettingsTab = (typeof SETTINGS_TABS)[number];

/**
 * Hashes RETIRADOS que siguen llevando a su pestaña, porque hay enlaces vivos que los usan.
 *
 * `tax` es el nombre con el que nació esta pestaña (PR #198, 24/07/2026) y con el que se quedó
 * mientras su rótulo pasaba a «Negocio»: dentro no hay impuestos, hay los datos de la empresa y su
 * certificado. Renombrarlo a secas NO era gratis — `verifactu` v1.5.35 está **publicada** con
 * `setup.route: "/settings#tax"`, los hubs en producción la tienen instalada, y un manifest
 * publicado no se reescribe (las rutas de Object Storage son inmutables por contrato). Como
 * {@link resolveSettingsTab} degrada en SILENCIO lo que no conoce, sin esta tabla el botón
 * «Configura VeriFactu» de cada módulo instalado aterrizaría en General sin nada que tocar — el
 * defecto que verifactu#49 ya tuvo que arreglar una vez. Por eso el alias no caduca.
 */
const RETIRED_HASHES: Record<string, SettingsTab> = { tax: 'business' };

/** Resuelve hashes actuales y degrada enlaces retirados/desconocidos al Hub actual. */
export function resolveSettingsTab(hash: string): SettingsTab {
  const candidate = hash.replace(/^#/, '');
  if ((SETTINGS_TABS as readonly string[]).includes(candidate)) return candidate as SettingsTab;
  return RETIRED_HASHES[candidate] ?? 'hub';
}
