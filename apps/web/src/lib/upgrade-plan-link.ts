// «Actualizar plan» — la salida del hub a la gestión del plan de ESTE hub, en el SaaS.
//
// ## Por qué esto SÍ y los siete de hub#479 NO
//
// hub#479 retiró siete controles que llevaban al pago desde dentro de la app, y con razón: eran
// botones «Comprar»/«Mejorar» con icono de carrito y la parrilla de precios al lado. Eso es un
// ESCAPARATE, y un escaparate dentro de la app es lo que miran Google Play y Microsoft Store.
//
// Lo que las tiendas regulan no es «¿hay un enlace?». La política de pagos apunta a **bienes
// digitales que se consumen dentro de la app** — cursos, capítulos, monedas de un juego. ERPlora es
// software B2B que un negocio usa para funcionar, y la suscripción se le factura a la EMPRESA, con
// su NIF, fuera de la app. Es la liga de Slack, QuickBooks o Shopify: todas en las tiendas, ninguna
// con billing de la tienda, todas con su enlace de cuenta. (Y en la UE el DMA obliga a permitir el
// steering de todos modos; el mercado de ERPlora es España.)
//
// La línea, entonces, no está en si hay botón sino en cómo se comporta:
//
//   gestión de cuenta ✅            escaparate ❌
//   «Actualizar plan»               «Mejora y ahorra un 20 %»
//   aterriza en la cuenta           parrilla de precios DENTRO de la ventana
//   etiqueta neutra                 icono de carrito
//
// Por eso el destino es la página de plan de ESE hub —la cuenta del cliente— y **no** el marketplace
// de planes, que sí es la superficie promocional y sigue siendo justo lo que hub#479 sacó de aquí.
//
// (El guard `no-purchase-steering.test.ts` es literal a propósito y salta hasta con una ruta escrita
// en un comentario; por eso aquí se nombra en prosa. Es lo que se quiere: mejor un falso positivo
// que reformulas en diez segundos que un enlace real que se cuela.)
import { config } from './config';
import type { DeviceContext } from './device';

/**
 * La página de plan de ESTE hub en el SaaS.
 *
 * Se construye a la carta: `config.hubId` lo resuelve el boot desde `GET /api/hub/context`, así que
 * un valor capturado al cargar el módulo sería el vacío del arranque.
 */
export function upgradePlanUrl(): string {
  const base = config.cloudApiUrl.replace(/\/+$/, '');
  return `${base}${upgradePlanPath()}`;
}

/**
 * La misma página **como ruta propia del SaaS**, que es lo que pide el pase de un solo uso (pm#196).
 *
 * Separada de [`upgradePlanUrl`] a propósito: la dirección la arma el runtime con SU idea de dónde
 * está el SaaS. Una página que pudiera elegir el host estaría eligiendo dónde se gasta el pase — y
 * el pase abre una sesión.
 */
export function upgradePlanPath(): string {
  return `/dashboard/hubs/${encodeURIComponent(config.hubId)}/change-plan/?utm_source=hub`;
}

/**
 * ¿Se le ofrece este control a la copia que tiene delante el usuario? (hub#756)
 *
 * El razonamiento de arriba —gestión de cuenta, no escaparate— sigue siendo el bueno, y para el
 * navegador y para Windows se mantiene entero: Microsoft lo permite **por escrito** (política
 * 10.8.2, un producto que no es juego puede usar su propia caja y mandar al navegador a
 * completarla).
 *
 * Lo que cambió no es el argumento sino un hecho: la QA sobre un Pixel real vio al revisor de Play
 * pulsar el botón, abrirse Chrome en la página de plan, y tratarlo como steering. Ante un envío que
 * te tumban, la lectura que cuenta es la de quien revisa.
 *
 * **El corte es la DISTRIBUCIÓN, no el sistema operativo**, y esa es toda la idea: la regla la pone
 * quien reparte el binario. Un APK instalado de lado corre en el mismo Android y Google no lo
 * gobierna; esconderle ahí su plan al dueño sería quitarle algo por una regla que no le aplica.
 *
 * Sin señal se OFRECE. Un shell anterior a hub#757 no manda `distribution`, y el navegador tampoco:
 * negar por defecto dejaría sin acceso a su plan a casi todo el mundo para protegerse de un riesgo
 * que fuera de Play no existe.
 */
export function planUpgradeIsOfferable(distribution: DeviceContext['distribution']): boolean {
  return distribution !== 'play';
}
