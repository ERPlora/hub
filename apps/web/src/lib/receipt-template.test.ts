// **Where the receipt template is configured** (hub#761).
//
// Ajustes → Tiques ofrecía una fila «Plantilla de tique · Configuración del recibo impreso y
// digital» pintada como botón (`ion-item button detail`) y **sin `@click`**: no navegaba, no abría
// nada y no explicaba nada. Un callejón sin salida en la configuración más básica de un TPV.
//
// La causa es que esa configuración **no vive en el shell**: vive en el módulo `printing`
// (cabecera y pie del tique, ancho de papel, auto-impresión y qué impresora la saca). El shell no
// puede tener una pantalla propia para eso sin duplicar el módulo, así que lo que le toca es
// **resolver a dónde llevar** — y decir la verdad cuando la app no está instalada, en vez de
// enseñar un botón que no hace nada.
import { describe, expect, it } from 'vitest';
import { receiptTemplateTarget, RECEIPT_TEMPLATE_MODULE } from './receipt-template';

/** Lo que `moduleNav` publica por cada módulo instalado: la ruta del shell que lo monta. */
const nav = (...ids: string[]) => ids.map((id) => ({ path: `/m/${id}` }));

describe('receiptTemplateTarget', () => {
  it('con la app de impresión instalada, lleva a SU pantalla de ajustes', () => {
    const target = receiptTemplateTarget(nav('sales', 'printing', 'taxes'));

    // `/m/printing/printing` = el módulo + su primera entrada de navegación, que es la de ajustes
    // (`erp-printing-settings`). Es la misma ruta que el propio manifest declara en su `setup`.
    expect(target.route).toBe('/m/printing/printing');
    expect(target.missingApp).toBe(false);
  });

  it('sin la app instalada NO promete configuración: manda a instalarla', () => {
    const target = receiptTemplateTarget(nav('sales', 'taxes'));

    // Lo contrario de lo que hacía: un destino real y accionable. El dueño no tiene por qué saber
    // que «la plantilla del tique» es una app que le falta — la pantalla se lo dice y le lleva.
    expect(target.missingApp).toBe(true);
    expect(target.route).toBe('/apps');
  });

  it('un hub sin módulos tampoco se queda sin salida', () => {
    expect(receiptTemplateTarget([])).toEqual({ route: '/apps', missingApp: true });
  });

  it('no se deja engañar por un módulo que solo EMPIECE por el mismo nombre', () => {
    // `/m/printing_labels` no es `/m/printing`. Con una comparación por prefijo, un módulo de
    // etiquetas haría creer al shell que la plantilla del tique ya se puede configurar, y la fila
    // volvería a llevar a una pantalla que no existe — el mismo callejón, disfrazado.
    const target = receiptTemplateTarget(nav('printing_labels'));

    expect(target.missingApp).toBe(true);
  });

  it('tolera lo que el runtime puede no haber cargado todavía', () => {
    // `moduleNav` arranca vacío y se rellena tras `GET /api/navigation`. Que la pantalla se pinte
    // antes no puede reventarla.
    expect(() => receiptTemplateTarget(undefined)).not.toThrow();
    expect(receiptTemplateTarget(undefined).missingApp).toBe(true);
  });

  it('nombra el módulo una sola vez, para que la vista no lo repita', () => {
    expect(RECEIPT_TEMPLATE_MODULE).toBe('printing');
  });
});
