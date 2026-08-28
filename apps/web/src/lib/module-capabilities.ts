// Lógica pura de los permisos (capabilities) que un módulo declara — extraída de AppsPage para
// poder testearla en el entorno node, igual que `apps-catalog.ts`.
//
// El problema que resuelve (pm#132, ADR-0079): el diálogo de consentimiento le preguntaba solo al
// RUNTIME local qué permisos declara un módulo. En una PRIMERA instalación el runtime todavía no
// conoce el módulo, así que la lista salía vacía, no había modal, y el módulo entraba con sus
// permisos en su estado por defecto — DENEGADO. El dueño aterrizaba en un «no tengo permiso» de un
// módulo recién instalado por él y al que nadie le preguntó nada.
//
// Ahora el catálogo del SaaS expone los ids que declara el manifest, y esa es la fuente cuando el
// runtime no sabe nada. Ojo con lo que NO cambia: el default-deny sigue intacto. Esto solo hace que
// se PREGUNTE; conceder sigue siendo un PUT explícito de un admin.

import type { ModuleCapability } from './runtime';

export interface CapabilityMeta {
  label: string;
  description: string;
  /**
   * i18n key of what STOPS WORKING while this permission is denied (hub#1174).
   *
   * A **key**, never a sentence: the owner reads it in their own language (ADR-0055/0199), and the
   * screen only translates it. It lives here — next to the capability it belongs to — so the
   * sentence is written ONCE and every surface that shows a denied permission says the same thing.
   *
   * Default-deny (ADR-0079) is the right default; a consequence nobody can see is not. With
   * `certificate` denied the hub issues invoices that never reach the tax authority; with `printer`
   * denied every ticket piles up in the queue.
   */
  breaksKey: string;
}

/**
 * Catálogo de respaldo de permisos conocidos: **espejo de
 * `crates/server/src/settings.rs::capability_meta`**.
 *
 * El servidor es la autoridad de las etiquetas y las manda en la respuesta del runtime; esto solo
 * se usa cuando no hay respuesta del runtime que usar — que es exactamente el caso de la primera
 * instalación, donde el Cloud manda **ids pelados** y hay que ponerles nombre aquí.
 *
 * Si añades una capability al core, añádela también aquí. Y si se te olvida, no desaparece:
 * `capabilityMeta` le pone un texto genérico y el modal la sigue enseñando (ver el test).
 */
export const CAPABILITY_CATALOG: Record<string, CapabilityMeta> = {
  network: {
    label: 'Acceso a internet',
    description: 'Permite al módulo conectarse a servidores externos (solo a los hosts declarados).',
    breaksKey: 'settings.capabilityBreaks.network',
  },
  certificate: {
    label: 'Certificado del negocio (firma fiscal)',
    description:
      'Permite usar el certificado de la empresa para firmar y transmitir documentos (p.ej. a Hacienda). '
      + 'La clave privada nunca sale del Hub.',
    breaksKey: 'settings.capabilityBreaks.certificate',
  },
  printer: {
    label: 'Impresora',
    // hub#1096 / ADR-0196: el Bridge se retiró. La impresión va por la cola del runtime del Hub,
    // que drena erplora-app (el dispositivo registrado como host de impresión). Espejo de
    // `capability_meta` en `crates/server/src/settings.rs` — un test clava que digan lo mismo.
    description:
      'Permite imprimir en las impresoras de ticket/cocina a través de la cola de impresión del Hub, '
      + 'que drena erplora-app como host de impresión.',
    breaksKey: 'settings.capabilityBreaks.printer',
  },
  notify: {
    label: 'Notificaciones',
    description: 'Permite enviar notificaciones por email, SMS o WhatsApp.',
    breaksKey: 'settings.capabilityBreaks.notify',
  },
  // hub#714. La descripción dice lo que el dueño arriesga, no el nombre técnico.
  manage_flows: {
    label: 'Administrar automatizaciones',
    description:
      'Permite crear, editar y borrar los flujos del hub, sus permisos y sus secretos. Un flujo ejecuta '
      + 'acciones en tu negocio sin nadie delante, así que concédelo solo al módulo con el que quieras editarlos.',
    breaksKey: 'settings.capabilityBreaks.manage_flows',
  },
};

const UNKNOWN: CapabilityMeta = {
  label: 'Permiso',
  description: 'Permiso solicitado por el módulo.',
  // A capability of the core this mirror has not learnt yet still has to say something: an empty
  // warning shouts at the owner without telling them anything.
  breaksKey: 'settings.capabilityBreaks.unknown',
};

/** Etiqueta y descripción de un permiso. Un id desconocido SE ENSEÑA igual, con texto genérico. */
export function capabilityMeta(id: string): CapabilityMeta {
  return CAPABILITY_CATALOG[id] ?? UNKNOWN;
}

/**
 * i18n key of what stops working while this permission is DENIED (hub#1174).
 *
 * The single source of that sentence. A screen must never type its own: the owner has to read the
 * same consequence in the consent modal and in Settings → Permissions.
 */
export function capabilityBreaksKey(id: string): string {
  return capabilityMeta(id).breaksKey;
}

/**
 * Construye las filas del modal a partir de ids pelados (lo único que trae el catálogo Cloud).
 *
 * `granted: false` SIEMPRE: el catálogo declara lo que el módulo pide, nunca lo que el hub le ha
 * concedido — eso solo lo sabe el runtime, y para un módulo aún no instalado la respuesta es «nada».
 */
export function capabilitiesFromIds(ids: readonly string[]): ModuleCapability[] {
  // Solo `label` y `description`: `ModuleCapability` es la forma que devuelve el RUNTIME, y
  // `breaksKey` es metadato de pantalla del shell — meterlo aquí lo colaría en un contrato ajeno.
  return ids.map((id) => {
    const { label, description } = capabilityMeta(id);
    return { id, label, description, requested: true, granted: false };
  });
}

/**
 * Qué permisos hay que poner delante del dueño antes de instalar.
 *
 * - **El runtime manda cuando sabe algo**: sus etiquetas vienen del servidor (al día y traducidas)
 *   y además conoce el estado real de concesión.
 * - **Si no sabe nada** —lista vacía o la llamada falló (`null`)— manda el catálogo Cloud. Este es
 *   el caso de la primera instalación, el único que importaba y el único que no estaba cubierto.
 * - **Lista vacía por los dos lados = el módulo no pide nada**: se instala sin modal, como los 24
 *   módulos publicados hasta hoy.
 */
export function capabilitiesToConsent(
  fromRuntime: readonly ModuleCapability[] | null,
  catalogIds: readonly string[],
): ModuleCapability[] {
  const requested = (fromRuntime ?? []).filter((c) => c.requested);
  return requested.length ? [...requested] : capabilitiesFromIds(catalogIds);
}
