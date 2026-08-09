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

/**
 * La página de plan de ESTE hub en el SaaS.
 *
 * Se construye a la carta: `config.hubId` lo resuelve el boot desde `GET /api/hub/context`, así que
 * un valor capturado al cargar el módulo sería el vacío del arranque.
 */
export function upgradePlanUrl(): string {
  const base = config.cloudApiUrl.replace(/\/+$/, '');
  return `${base}/dashboard/hubs/${encodeURIComponent(config.hubId)}/change-plan/?utm_source=hub`;
}
