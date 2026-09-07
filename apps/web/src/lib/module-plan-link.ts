// El plan de UN módulo, en la CUENTA del cliente — el destino al que la pestaña «Plan» sí puede
// enlazar (hub#1608).
//
// ## Por qué no vale la ficha del marketplace
//
// Es la superficie promocional del catálogo, y es una de las tres direcciones que
// `no-purchase-steering.test.ts` prohíbe nombrar desde el Hub (hub#479). Lo que sí está permitido
// —y lo razona entero `upgrade-plan-link.ts`— es aterrizar en la CUENTA: gestión de lo que el
// cliente ya tiene, etiqueta neutra, y el precedente vivo es «Actualizar plan» del menú lateral.
//
// La página de cuenta por módulo la abrió ERPlora/saas#1901 en
// `/dashboard/hubs/<hub_id>/modules/<slug>/plan/`: misma vista que la ficha, con el hub resuelto
// por la RUTA. Ese detalle es el que arregla la queja de Ioan sobre el enlace del menú: con el hub
// y el módulo en la dirección, quien pulsa sabe de qué plan se le está hablando.
import { config } from './config';

/**
 * La página de plan de ESE módulo para ESTE hub, como ruta propia del SaaS.
 *
 * Ruta y no URL absoluta porque es lo que pide el pase de un solo uso (pm#196): la dirección la
 * arma el runtime con SU idea de dónde está el SaaS. Una página que pudiera elegir el host estaría
 * eligiendo dónde se gasta el pase — y el pase abre una sesión.
 *
 * Se lee en el momento de pulsar: `config.hubId` lo resuelve el boot desde `GET /api/hub/context`,
 * así que un valor capturado al cargar el módulo sería el vacío del arranque.
 */
export function modulePlanPath(moduleId: string): string {
  const hub = encodeURIComponent(config.hubId);
  const mod = encodeURIComponent(moduleId);
  return `/dashboard/hubs/${hub}/modules/${mod}/plan/?utm_source=hub`;
}

/** La misma página en absoluto, para el caso degradado en que no se pueda acuñar el pase. */
export function modulePlanUrl(moduleId: string): string {
  const base = config.cloudApiUrl.replace(/\/+$/, '');
  return `${base}${modulePlanPath(moduleId)}`;
}
