// hub#338 — lo que el usuario LEE cuando un escaneo de impresoras termina sin lista.
//
// Un escaneo puede acabar sin impresoras por dos motivos opuestos, y hasta ahora se veían igual
// (una lista vacía, sin un solo error):
//
//   · con permiso y sin impresoras → «conecta una impresora» — el TPV miró y no había nada;
//   · sin permiso de red local     → «dale permiso a la app» — el TPV no llegó a mirar.
//
// Darle al usuario la frase equivocada le cuesta la tarde: se pone a revisar una impresora que
// lleva encendida todo el rato, o a tocar ajustes del sistema que ya estaban bien.
//
// El copy vive AQUÍ y no en cada módulo: es el shell quien tiene i18n, y la frase tiene que ser
// la misma la pida quien la pida (módulo printing, ajustes, un asistente…).
//
// Desde ADR-0196 §3 hay un tercer final, y no es del escaneo sino de antes: en un navegador sin la
// app instalada no hay ningún camino al hardware → `hardwareUnavailableMessage()`.
import { i18n } from '../i18n';

/**
 * Los dos finales de un escaneo sin lista. Deliberadamente NO hay un tercero: cualquier otro
 * fallo es un error de hardware corriente y ya tiene su propio mensaje.
 */
export type PrinterDiscoveryOutcome = 'permission_denied' | 'no_printers';

/** La frase que hay que enseñar, en el idioma activo del hub. */
export function printerDiscoveryMessage(outcome: PrinterDiscoveryOutcome): string {
  const key = outcome === 'permission_denied' ? 'hardware.printersBlocked' : 'hardware.printersNone';
  return i18n.global.t(key);
}

/**
 * Lo que se lee cuando en ESTE dispositivo no hay ningún camino al hardware (ADR-0196 §3): un
 * navegador a secas, sin la app instalada.
 *
 * No es un tercer final del escaneo —por eso no entra en {@link PrinterDiscoveryOutcome}—: el
 * escaneo ni siquiera empieza. Y no es «no me dejan mirar la red»: allí hay app y falta un permiso
 * que el usuario puede conceder; aquí lo que falta es la app. Mandarle a los ajustes del sistema a
 * buscar un permiso que no existe le costaría la tarde, que es justo el fallo de hub#338.
 *
 * Vive junto al resto del copy de hardware por lo mismo que aquel: es el shell quien tiene i18n, y
 * la frase tiene que ser la misma la pida quien la pida.
 */
export function hardwareUnavailableMessage(): string {
  return i18n.global.t('hardware.unavailable');
}
