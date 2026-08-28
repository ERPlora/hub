// @vitest-environment happy-dom
// El adjuntador de un documento del otorgamiento (hub#1293).
//
// Existe porque esa pantalla pide hasta CUATRO ficheros —el modelo firmado, la copia del documento
// de identidad, la muestra de firma y el justificante de representación— y cada uno llevaba el
// mismo trío: un `<input type="file">` escondido, un botón que lo dispara y un nombre que enseñar.
// Cuatro copias de eso son cuatro sitios donde el `accept` se puede quedar desparejado del botón.
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';

// `HubIcon` arrastra el set de Iconify por `~icons/*`, que el runner no resuelve: aquí no se está
// probando el icono.
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import GrantFilePicker from './GrantFilePicker.vue';

function mountPicker(props: Record<string, unknown> = {}) {
  return mount(GrantFilePicker, {
    props: { label: 'Attach the signed model', testid: 'grant-signed-document', ...props },
    global: { renderStubDefaultSlot: true },
    shallow: true,
  });
}

describe('el adjuntador', () => {
  it('emite el fichero que la persona eligió', async () => {
    const w = mountPicker();
    const file = new File([new Uint8Array([1])], 'anexo.pdf', { type: 'application/pdf' });
    const input = w.get('input[type="file"]');
    Object.defineProperty(input.element, 'files', { value: [file] });

    await input.trigger('change');

    expect(w.emitted('picked')?.[0]).toEqual([file]);
  });

  it('un diálogo cancelado emite `null`, no se queda con el de antes', async () => {
    // Sin esto, quitar un adjunto es imposible: el botón seguiría enseñando un nombre que ya no
    // corresponde a nada, y se enviaría el fichero anterior.
    const w = mountPicker();
    const input = w.get('input[type="file"]');
    Object.defineProperty(input.element, 'files', { value: [] });

    await input.trigger('change');

    expect(w.emitted('picked')?.[0]).toEqual([null]);
  });

  it('el `accept` que se le pide es el que lleva el input: si no, el filtro no filtra', async () => {
    const w = mountPicker({ accept: '.pdf,application/pdf' });

    expect(w.get('input[type="file"]').attributes('accept')).toBe('.pdf,application/pdf');
  });

  it('el testid identifica al input, que es lo que un e2e tiene que rellenar', () => {
    const w = mountPicker({ testid: 'grant-dni-copy' });

    expect(w.find('[data-testid="grant-dni-copy"]').exists()).toBe(true);
  });
});
