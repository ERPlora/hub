// Lo destructivo pide MÁS que un clic (hub#1042).
//
// La pasada de QA pidió «borra todas las citas de la agenda». No se borró ninguna — pero no por un
// control: el modelo improvisó una negativa, y un turno después listó `bulk_delete` entre sus
// tools. Que hoy no se borre nada es una propiedad emergente del criterio del modelo, no una
// cerradura. Y el producto además LE MINTIÓ al usuario sobre sus propias defensas, que es peor que
// no tenerlas: quien lee «es una protección intencional» deja de tener cuidado.
//
// `ai.risk` ya viaja hasta la tarjeta (ya en develop). Esto es la política que lo USA.
//
// Las dos formas salen del mercado, tabla en la issue: la confirmación ESCRITA es el patrón de
// GitHub para borrar un repo, y enseñar el número afectado ANTES es lo que hacen BC (panel con
// las líneas resueltas) y SAP Joule (tarjeta con los datos, con salida a Editar o Descartar).

import { describe, expect, it } from 'vitest';

import { confirmationFor } from './assistant-danger';

describe('confirmationFor — cuánto se le pide al usuario', () => {
  it('lo corriente se confirma con un clic, como siempre', () => {
    const c = confirmationFor({ risk: 'normal', args: { name: 'Corte' } });

    expect(c.kind).toBe('click');
  });

  // Sin marca = normal. La inmensa mayoría del catálogo no la declara todavía, y exigir texto
  // escrito para crear un servicio enseñaría a teclear sin leer — que es como se pierde el efecto.
  it('sin marca se trata como corriente', () => {
    const c = confirmationFor({ args: {} });

    expect(c.kind).toBe('click');
  });

  it('lo destructivo exige ESCRIBIR, no basta con pulsar', () => {
    const c = confirmationFor({ risk: 'destructive', args: { id: 'x' } });

    expect(c.kind).toBe('typed');
  });
});

describe('confirmationFor — el borrado masivo dice CUÁNTOS', () => {
  it('cuenta el conjunto que nombra el propio payload', () => {
    const c = confirmationFor({
      risk: 'bulk_destructive',
      args: { ids: ['a', 'b', 'c', 'd'] },
    });

    expect(c.kind).toBe('typed');
    expect(c.affected).toBe(4);
    // Se escribe el NÚMERO: es lo que obliga a leerlo. Escribir «BORRAR» se teclea sin mirar.
    expect(c.expected).toBe('4');
  });

  it('coge el array más grande cuando el payload trae varios', () => {
    const c = confirmationFor({
      risk: 'bulk_destructive',
      args: { ids: ['a', 'b', 'c'], tags: ['x'] },
    });

    expect(c.affected).toBe(3);
  });

  // El caso peligroso de verdad: un masivo cuyo payload NO nombra el conjunto (un filtro, un
  // «todas»). No se puede decir cuántas caen, así que no se ofrece el atajo — se manda a la
  // pantalla, que sí las enseña.
  it('si no puede contar cuántas son, NO se ejecuta desde el chat', () => {
    const c = confirmationFor({ risk: 'bulk_destructive', args: { filter: 'all' } });

    expect(c.kind).toBe('refuse');
    expect(c.affected).toBeUndefined();
  });

  it('un conjunto vacío tampoco pasa por buenas', () => {
    const c = confirmationFor({ risk: 'bulk_destructive', args: { ids: [] } });

    expect(c.kind).toBe('refuse');
  });
});
