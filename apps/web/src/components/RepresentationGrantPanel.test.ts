// @vitest-environment happy-dom
// Contrato de la pantalla del otorgamiento de representación (hub#1293 — rehace hub#817).
//
// 🔴 Lo que esto cierra: la pantalla hacía firmar con un TRAZO en un canvas sobre una PARÁFRASIS del
// Anexo I compuesta por el runtime. La FAQ de colaboración social de la AEAT admite exactamente dos
// firmas —manuscrita sobre el modelo impreso (con sello si el otorgante es sociedad) o electrónica
// con certificado cualificado del propio cliente— y el modelo oficial dice que su texto «no podrá
// ser modificado». Un trazo en pantalla no es ninguna de las dos, y un sello no cabe en un canvas.
//
// El flujo que sí vale: descargar el modelo oficial que sirve el SaaS → firmarlo FUERA → subirlo →
// esperar a que lo revise una persona (24-72 h). Nada se pone `vigente` solo.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const getRepresentationGrant = vi.fn();
const postRepresentationGrant = vi.fn();
const downloadRepresentationGrantModel = vi.fn();
const saveDownload = vi.fn();
const openExternal = vi.fn();

// `vi.mock` se iza por encima de todo, así que la clase que la factoría devuelve tiene que existir
// ANTES: `vi.hoisted` es la única forma de declararla arriba del todo sin duplicarla.
const { RepresentationGrantError } = vi.hoisted(() => ({
  RepresentationGrantError: class RepresentationGrantError extends Error {
    readonly code?: string;
    readonly statusCode?: number;
    constructor(message: string, code?: string, statusCode?: number) {
      super(message);
      this.name = 'RepresentationGrantError';
      this.code = code;
      this.statusCode = statusCode;
    }
  },
}));

vi.mock('../lib/runtime', () => ({
  RepresentationGrantError,
  getRepresentationGrant: (...a: unknown[]) => getRepresentationGrant(...a),
  postRepresentationGrant: (...a: unknown[]) => postRepresentationGrant(...a),
  downloadRepresentationGrantModel: (...a: unknown[]) => downloadRepresentationGrantModel(...a),
}));
vi.mock('../lib/session', () => ({ isAdmin: { value: true } }));
vi.mock('../lib/save-download', () => ({
  saveDownload: (...a: unknown[]) => saveDownload(...a),
  saveDownloadMessageKey: () => 'download.failed',
  SaveDownloadError: class extends Error {},
}));
vi.mock('../lib/open-external', () => ({ openExternal: (...a: unknown[]) => openExternal(...a) }));
vi.mock('../lib/config', () => ({
  config: { hubId: 'hub-abc', cloudApiUrl: 'https://erplora.com' },
}));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import RepresentationGrantPanel from './RepresentationGrantPanel.vue';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(RepresentationGrantPanel, {
    props: { obligadoNif: 'B12345674', obligadoName: 'Bar Manolo SL', ...props },
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
}

type Panel = {
  status: string;
  rejectedReason: string;
  obligadoMunicipio: string;
  obligadoVia: string;
  obligadoNumero: string;
  signerNif: string;
  signerName: string;
  signerMunicipio: string;
  signerVia: string;
  signerNumero: string;
  documentType: 'dni' | 'nie';
  signedDocument: File | null;
  dniFile: File | null;
  signatureSample: File | null;
  representationProof: File | null;
  needsSignatureSample: boolean;
  needsRepresentationProof: boolean;
  canDownloadModel: boolean;
  canSubmit: boolean;
  errorKey: string;
  downloadModel: () => Promise<void>;
  submit: () => Promise<void>;
  openDashboard: () => Promise<void>;
};

function vm(wrapper: ReturnType<typeof mountPanel>): Panel {
  return wrapper.vm as unknown as Panel;
}

function pdf(name = 'anexo-i.pdf') {
  return new File([new Uint8Array([1, 2, 3])], name, { type: 'application/pdf' });
}
function image(name = 'dni.jpg') {
  return new File([new Uint8Array([4, 5])], name, { type: 'image/jpeg' });
}

/** Deja el paso 1 relleno: es lo mínimo para poder pedir el modelo. */
function fillModelFields(panel: Panel) {
  panel.signerNif = '12345678Z';
  panel.signerName = 'Manolo García';
}

/** Deja el paso 2 relleno para una SOCIEDAD con DNI: modelo firmado + DNI + justificante. */
function fillUpload(panel: Panel) {
  panel.signedDocument = pdf();
  panel.dniFile = image();
  panel.representationProof = pdf('escritura.pdf');
}

beforeEach(() => {
  getRepresentationGrant.mockReset();
  getRepresentationGrant.mockResolvedValue({
    status: 'absent',
    at: '',
    rejected_reason: '',
    signature_kind: '',
    document_type: '',
  });
  postRepresentationGrant.mockReset();
  postRepresentationGrant.mockResolvedValue({ status: 'pendiente', at: '2026-08-28T09:00:00Z' });
  downloadRepresentationGrantModel.mockReset();
  downloadRepresentationGrantModel.mockResolvedValue(
    new Blob(['%PDF-1.7'], { type: 'application/pdf' }),
  );
  saveDownload.mockReset();
  saveDownload.mockResolvedValue(null);
  openExternal.mockReset();
  openExternal.mockResolvedValue(undefined);
});

describe('lo que la pantalla ya NO hace', () => {
  it('🔴 no hay canvas de firma: un trazo no es ninguna de las dos vías que admite la AEAT', async () => {
    const w = mountPanel();
    await flushPromises();

    expect(w.find('canvas').exists()).toBe(false);
    expect(w.find('[data-testid="grant-canvas"]').exists()).toBe(false);
  });

  it('🔴 tampoco compone el documento: el texto del modelo no vive en el Hub', async () => {
    const w = mountPanel();
    await flushPromises();

    // El GET ya no devuelve `anexo_text`, y la pantalla no lo pinta desde ningún sitio.
    expect(w.html()).not.toContain('OTORGA su representación');
    expect(w.find('[data-testid="grant-anexo"]').exists()).toBe(false);
  });
});

describe('paso 1 · el modelo oficial', () => {
  it('se pide al runtime con los datos de las dos partes y se GUARDA con save-download', async () => {
    // `save-download` y no un `<a download>`: dentro de la app instalada en Android el ancla no
    // hace literalmente nada, y este es el fichero que el cliente tiene que firmar.
    const w = mountPanel({ obligadoAddress: 'Rúa do Príncipe 10' });
    await flushPromises();
    const panel = vm(w);
    fillModelFields(panel);

    await panel.downloadModel();

    expect(downloadRepresentationGrantModel).toHaveBeenCalledTimes(1);
    const sent = downloadRepresentationGrantModel.mock.calls[0][0] as Record<string, string>;
    expect(sent.obligado_nif).toBe('B12345674');
    expect(sent.obligado_name).toBe('Bar Manolo SL');
    expect(sent.signer_nif).toBe('12345678Z');
    // La dirección del negocio que ya está configurada se aprovecha: nadie la escribe dos veces.
    expect(sent.obligado_via).toBe('Rúa do Príncipe 10');
    expect(saveDownload).toHaveBeenCalledTimes(1);
    expect(saveDownload.mock.calls[0][1]).toBeInstanceOf(Blob);
  });

  it('sin firmante no se puede pedir: un modelo en blanco es un papel firmado para nada', async () => {
    const w = mountPanel();
    await flushPromises();

    expect(vm(w).canDownloadModel).toBe(false);
  });

  it('🔴 si el SaaS aún no tiene la ruta (404) se DICE, no se queda en blanco', async () => {
    downloadRepresentationGrantModel.mockRejectedValueOnce(
      new RepresentationGrantError('representation-grant-model → 502', 'cloud_rejected', 404),
    );
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillModelFields(panel);

    await panel.downloadModel();

    expect(panel.errorKey).toBe('grant.errors.cloud_rejected');
  });
});

describe('paso 2 · la subida', () => {
  it('manda el modelo firmado, la copia del documento y el tipo, y NO manda un trazo', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillUpload(panel);

    await panel.submit();

    expect(postRepresentationGrant).toHaveBeenCalledTimes(1);
    const sent = postRepresentationGrant.mock.calls[0][0] as Record<string, unknown>;
    expect(sent.signed_document).toBeInstanceOf(File);
    expect(sent.dni_copy).toBeInstanceOf(File);
    expect(sent.document_type).toBe('dni');
    expect(sent.signature).toBeUndefined();
  });

  it('🔴 con NIE hace falta una muestra de firma, y sin ella no se envía', async () => {
    // Muchos documentos de identidad extranjeros no llevan firma impresa, y ERPlora responde de la
    // autenticidad de la del otorgante: sin nada con que compararla, el revisor no puede.
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillUpload(panel);
    panel.documentType = 'nie';
    await flushPromises();

    expect(panel.needsSignatureSample).toBe(true);
    expect(panel.canSubmit).toBe(false);

    panel.signatureSample = image('firma.jpg');
    await flushPromises();
    expect(panel.canSubmit).toBe(true);
  });

  it('🔴 una SOCIEDAD tiene que acreditar quién firma por ella; un autónomo no', async () => {
    const company = mountPanel();
    await flushPromises();
    const panel = vm(company);
    panel.signedDocument = pdf();
    panel.dniFile = image();
    await flushPromises();

    expect(panel.needsRepresentationProof).toBe(true);
    expect(panel.canSubmit).toBe(false);

    const person = mountPanel({ obligadoNif: '12345678Z', obligadoName: 'Manolo García' });
    await flushPromises();
    const solo = vm(person);
    solo.signedDocument = pdf();
    solo.dniFile = image();
    await flushPromises();

    expect(solo.needsRepresentationProof).toBe(false);
    expect(solo.canSubmit).toBe(true);
  });

  it('tras subir queda PENDIENTE: nada se pone vigente solo', async () => {
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillUpload(panel);

    await panel.submit();

    expect(panel.status).toBe('pendiente');
  });

  it('🔴 el rechazo del runtime se pinta POR CÓDIGO, no por su frase', async () => {
    postRepresentationGrant.mockRejectedValueOnce(
      new RepresentationGrantError('post → 400', 'signed_document_not_pdf'),
    );
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillUpload(panel);

    await panel.submit();

    expect(panel.errorKey).toBe('grant.errors.signed_document_not_pdf');
  });

  it('un fallo NO borra lo que la persona acaba de adjuntar', async () => {
    postRepresentationGrant.mockRejectedValueOnce(new Error('offline'));
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillUpload(panel);

    await panel.submit();

    expect(panel.signedDocument).not.toBeNull();
    expect(panel.dniFile).not.toBeNull();
  });

  it('🔒 en el camino de éxito el Hub OLVIDA los documentos', async () => {
    // RGPD: la custodia es del SaaS. Un hub que se los queda los mete en cada backup y en cada
    // blueprint que exporte.
    const w = mountPanel();
    await flushPromises();
    const panel = vm(w);
    fillUpload(panel);

    await panel.submit();

    expect(panel.signedDocument).toBeNull();
    expect(panel.dniFile).toBeNull();
    expect(panel.representationProof).toBeNull();
  });
});

describe('lo que se lee en pantalla', () => {
  it('🔴 las DOS direcciones se distinguen: «Municipio/Vía/Número» aparece dos veces', async () => {
    // Detectado mirando la pantalla a 390/768/1280: los tres campos de dirección salían repetidos
    // sin nada que dijera cuál es la del negocio y cuál la de quien firma. Dos bloques idénticos
    // seguidos es exactamente cómo se rellena el segundo con los datos del primero.
    const w = mountPanel();
    await flushPromises();

    expect(w.find('[data-testid="grant-party-obligado"]').exists()).toBe(true);
    expect(w.find('[data-testid="grant-party-signer"]').exists()).toBe(true);
  });

  it('con el otorgamiento en revisión NO se invita a volver a hacerlo', async () => {
    // «Lo descargas, lo firmas y lo vuelves a subir» debajo de «lo estamos revisando» es lo que
    // produce el segundo envío que otra persona tiene que desempatar a mano.
    getRepresentationGrant.mockResolvedValue({
      status: 'pendiente',
      at: '2026-08-28T09:00:00Z',
      rejected_reason: '',
      signature_kind: '',
      document_type: 'dni',
    });

    const w = mountPanel();
    await flushPromises();

    expect(w.find('[data-testid="grant-intro"]').exists()).toBe(false);
    expect(w.find('[data-testid="grant-submit"]').exists()).toBe(false);
  });
});

describe('el estado', () => {
  it('«pendiente» es un estado propio: se está revisando', async () => {
    getRepresentationGrant.mockResolvedValue({
      status: 'pendiente',
      at: '2026-08-28T09:00:00Z',
      rejected_reason: '',
      signature_kind: 'handwritten',
      document_type: 'dni',
    });

    const w = mountPanel();
    await flushPromises();

    expect(vm(w).status).toBe('pendiente');
    expect(w.find('[data-testid="grant-state-pendiente"]').exists()).toBe(true);
  });

  it('🔴 «rechazado» enseña el MOTIVO: es lo único con lo que el cliente puede actuar', async () => {
    getRepresentationGrant.mockResolvedValue({
      status: 'rechazado',
      at: '2026-08-29T10:00:00Z',
      rejected_reason: 'La copia del DNI está ilegible.',
      signature_kind: '',
      document_type: 'dni',
    });

    const w = mountPanel();
    await flushPromises();

    expect(vm(w).rejectedReason).toContain('ilegible');
    expect(w.text()).toContain('ilegible');
  });

  it('si el runtime no contesta, no se inventa un estado', async () => {
    getRepresentationGrant.mockRejectedValue(new Error('offline'));

    const w = mountPanel();
    await flushPromises();

    expect(vm(w).status).toBe('');
  });
});

describe('la salida al ordenador', () => {
  it('abre el dashboard del Cloud POR FUERA, nunca llevándose esta ventana', async () => {
    // Dentro de la app instalada el webview no tiene barra ni Atrás: navegar en sitio deja al
    // usuario atrapado en el SaaS sin vuelta.
    const w = mountPanel();
    await flushPromises();

    await vm(w).openDashboard();

    expect(openExternal).toHaveBeenCalledTimes(1);
    expect(openExternal.mock.calls[0][0]).toBe(
      'https://erplora.com/dashboard/hubs/hub-abc/fiscal/representation-grant/',
    );
  });
});
