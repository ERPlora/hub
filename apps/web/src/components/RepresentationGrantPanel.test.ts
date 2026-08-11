// @vitest-environment happy-dom
// Contrato de la pantalla donde el cliente FIRMA el otorgamiento de representación (hub#817).
//
// 🔴 El agujero que esto cierra: `saas#1252` dejó el modelo, el servicio, la API y el admin… y la
// pantalla sin hacer. La única forma de crear un otorgamiento era llamar a la API a mano, así que
// un cliente real no podía firmar. Un mecanismo sin puerta.
//
// Lo que NO vale (requisito legal, no de producto): una casilla de «acepto». La FAQ de
// desarrolladores de la AEAT v1.3 §16.4 admite formularios web, pero **exige** «la cumplimentación
// y firma (incluyendo electrónica) del otorgamiento» — y el representante responde de la
// autenticidad de la firma y de la copia del DNI. De ahí que este contrato exija trazo + DNI, y no
// deje enviar sin los dos.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const getRepresentationGrant = vi.fn();
const postRepresentationGrant = vi.fn();

vi.mock('../lib/runtime', () => ({
  getRepresentationGrant: (...a: unknown[]) => getRepresentationGrant(...a),
  postRepresentationGrant: (...a: unknown[]) => postRepresentationGrant(...a),
}));
vi.mock('../lib/session', () => ({ isAdmin: { value: true } }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import RepresentationGrantPanel from './RepresentationGrantPanel.vue';

// Como lo sirve el runtime: con sus placeholders, que es lo que el panel rellena para que la
// persona lea el documento CON sus datos dentro y no una plantilla en blanco.
const ANEXO =
  'OTORGAMIENTO DE LA REPRESENTACIÓN DIRECTA … VERI*FACTU … BOE-A-2024-27600. ' +
  'DON/DOÑA {signer_name}, con NIF/NIE {signer_nif} … OBLIGADO TRIBUTARIO REPRESENTADO: ' +
  '{obligado_name}, con NIF {obligado_nif}.';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(RepresentationGrantPanel, {
    props: { obligadoNif: 'B12345678', obligadoName: 'Bar Manolo SL', ...props },
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
}

type Panel = {
  anexoText: string;
  status: string;
  signerNif: string;
  signerName: string;
  signature: string;
  dniFile: File | null;
  confirmed: boolean;
  canSubmit: boolean;
  submit: () => Promise<void>;
};

function vm(wrapper: ReturnType<typeof mountPanel>): Panel {
  return wrapper.vm as unknown as Panel;
}

/** Deja el formulario completo: firmante + trazo + DNI + confirmación explícita. */
function fillIn(panel: Panel) {
  panel.signerNif = '12345678Z';
  panel.signerName = 'Manolo García';
  panel.signature = 'data:image/png;base64,iVBORw0KGgo=';
  panel.dniFile = new File([new Uint8Array([1, 2, 3])], 'dni.jpg', { type: 'image/jpeg' });
  panel.confirmed = true;
}

beforeEach(() => {
  getRepresentationGrant.mockReset();
  getRepresentationGrant.mockResolvedValue({ status: 'absent', at: '', anexo_text: ANEXO });
  postRepresentationGrant.mockReset();
  postRepresentationGrant.mockResolvedValue({ status: 'vigente', at: '2026-08-11T09:00:00Z' });
});

describe('el texto que se firma', () => {
  it('se muestra ENTERO en la pantalla, no detrás de un enlace', async () => {
    const w = mountPanel();
    await flushPromises();

    expect(vm(w).anexoText).toContain('VERI*FACTU');
    expect(w.text()).toContain('BOE-A-2024-27600');
  });

  it('lo sirve el runtime, para que lo leído y lo archivado sean la MISMA cadena', async () => {
    // Una copia en el bundle de i18n sería el mismo documento diciendo dos cosas.
    mountPanel();
    await flushPromises();

    expect(getRepresentationGrant).toHaveBeenCalled();
  });
});

describe('el obligado', () => {
  it('viene del perfil fiscal del Hub y NO se puede editar aquí', async () => {
    const w = mountPanel();
    await flushPromises();

    // Aparece DENTRO del documento que se lee, ya sustituido.
    expect(w.text()).toContain('B12345678');
    expect(w.text()).toContain('Bar Manolo SL');
    // Y en sus campos, en SOLO LECTURA: se cambia donde se configura la identidad fiscal, no
    // dentro del documento que se firma — el NIF del obligado ancla la cadena y viaja como
    // `IDEmisorFactura`.
    const nif = w.get('[data-testid="grant-obligado-nif"]');
    const name = w.get('[data-testid="grant-obligado-name"]');
    expect(nif.attributes('value')).toBe('B12345678');
    expect(name.attributes('value')).toBe('Bar Manolo SL');
    expect(nif.attributes('readonly')).toBeDefined();
    expect(name.attributes('readonly')).toBeDefined();
  });
});

describe('qué hace falta para poder firmar', () => {
  it('una casilla de «acepto» NO basta: sin trazo no se envía', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);
    panel.signature = '';

    expect(panel.canSubmit).toBe(false);
  });

  it('sin la copia del DNI tampoco', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);
    panel.dniFile = null;

    expect(panel.canSubmit).toBe(false);
  });

  it('sin el firmante tampoco — y el firmante es una PERSONA, no la sociedad', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);
    panel.signerNif = '';

    expect(panel.canSubmit).toBe(false);
  });

  it('sin confirmación explícita tampoco', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);
    panel.confirmed = false;

    expect(panel.canSubmit).toBe(false);
  });

  it('con todo puesto, sí', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);

    expect(panel.canSubmit).toBe(true);
  });
});

describe('lo que se envía', () => {
  it('manda el NIF del NEGOCIO como obligado, nunca otro', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);

    await panel.submit();

    expect(postRepresentationGrant).toHaveBeenCalledTimes(1);
    const sent = postRepresentationGrant.mock.calls[0][0] as Record<string, unknown>;
    expect(sent.obligado_nif).toBe('B12345678');
    expect(sent.obligado_name).toBe('Bar Manolo SL');
    expect(sent.signer_nif).toBe('12345678Z');
    expect(sent.signer_name).toBe('Manolo García');
    expect(sent.signature).toBeInstanceOf(Blob);
    expect(sent.dni_copy).toBeInstanceOf(File);
  });

  it('🔒 el Hub OLVIDA el trazo y el DNI en cuanto salen', async () => {
    // RGPD: la custodia es del SaaS. Un hub que se los queda los mete en cada backup y en cada
    // blueprint que exporte.
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);

    await panel.submit();

    expect(panel.signature).toBe('');
    expect(panel.dniFile).toBeNull();
  });

  it('un fallo del runtime NO borra lo que la persona acaba de rellenar', async () => {
    postRepresentationGrant.mockRejectedValueOnce(new Error('cloud_rejected'));
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);

    await panel.submit();

    expect(panel.signature).not.toBe('');
    expect(panel.dniFile).not.toBeNull();
  });
});

describe('el estado del otorgamiento', () => {
  it('se pinta al cargar', async () => {
    getRepresentationGrant.mockResolvedValue({
      status: 'vigente',
      at: '2026-08-11T09:00:00Z',
      anexo_text: ANEXO,
    });

    const w = mountPanel();
    await flushPromises();

    expect(vm(w).status).toBe('vigente');
  });

  it('«revocado» es un estado propio: el cliente puede revocar solo y sin avisarnos', async () => {
    getRepresentationGrant.mockResolvedValue({
      status: 'revocado',
      at: '2026-08-11T10:00:00Z',
      anexo_text: ANEXO,
    });

    const w = mountPanel();
    await flushPromises();

    expect(vm(w).status).toBe('revocado');
  });

  it('tras firmar, pasa a vigente sin recargar la página', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillIn(panel);

    await panel.submit();

    expect(panel.status).toBe('vigente');
  });

  it('si el runtime no contesta, no se inventa un estado', async () => {
    getRepresentationGrant.mockRejectedValue(new Error('offline'));

    const w = mountPanel();
    await flushPromises();

    expect(vm(w).status).toBe('');
  });
});
