// hub#1293 — el otorgamiento se firma FUERA, sobre el modelo oficial que sirve el SaaS.
//
// Lo que este contrato protege es lo que la pantalla necesita para no quedarse en blanco:
//
//  1. El modelo llega como PDF de verdad (un `Blob`), no como JSON ni como texto: lo que se guarda
//     en el disco del cliente y luego se firma con AutoFirma tiene que ser el fichero, entero.
//  2. Un rechazo llega con su CÓDIGO (`signed_document_not_pdf`, `signature_sample_required`…) y,
//     cuando el que rechaza es el plano de control, con su `status_code`. Mientras el SaaS nuevo no
//     esté desplegado esa ruta contesta **404**, y «404» es algo que una persona puede entender;
//     un botón que no hace nada, no.
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  RepresentationGrantError,
  downloadRepresentationGrantModel,
  getRepresentationGrant,
  postRepresentationGrant,
} from './runtime';

function respondWith(status: number, body: unknown, contentType = 'application/json'): void {
  const ok = status >= 200 && status < 300;
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok,
      status,
      headers: { get: () => contentType },
      json: () => Promise.resolve(body),
      blob: () => Promise.resolve(new Blob([body as BlobPart], { type: contentType })),
    }),
  );
}

function modelFields() {
  return {
    obligado_nif: 'B12345674',
    obligado_name: 'Bar Manolo SL',
    obligado_municipio: 'Vigo',
    obligado_via: 'Rúa do Príncipe',
    obligado_numero: '10',
    signer_nif: '12345678Z',
    signer_name: 'Manolo García',
    signer_municipio: '',
    signer_via: '',
    signer_numero: '',
  };
}

function capture() {
  return {
    obligado_nif: 'B12345674',
    obligado_name: 'Bar Manolo SL',
    signer_nif: '12345678Z',
    signer_name: 'Manolo García',
    document_type: 'dni' as const,
    signed_document: new File([new Uint8Array([1])], 'anexo.pdf', { type: 'application/pdf' }),
    dni_copy: new File([new Uint8Array([2])], 'dni.jpg', { type: 'image/jpeg' }),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('el modelo oficial', () => {
  it('se descarga como PDF, no como JSON: es el fichero que el cliente firma', async () => {
    respondWith(200, '%PDF-1.7', 'application/pdf');

    const pdf = await downloadRepresentationGrantModel(modelFields());

    expect(pdf).toBeInstanceOf(Blob);
    const [url, init] = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock
      .calls[0] as [string, RequestInit];
    expect(url).toContain('/api/fiscal/representation-grant/model');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toMatchObject({ obligado_nif: 'B12345674' });
  });

  it('🔴 un SaaS que todavía no tiene la ruta (404) se DICE, con su status', async () => {
    respondWith(502, { ok: false, error: 'cloud_rejected', status_code: 404 });

    const err = (await downloadRepresentationGrantModel(modelFields()).catch(
      (e: unknown) => e,
    )) as RepresentationGrantError;

    expect(err).toBeInstanceOf(RepresentationGrantError);
    expect(err.code).toBe('cloud_rejected');
    expect(err.statusCode).toBe(404);
  });

  it('un rechazo del propio runtime conserva su código', async () => {
    respondWith(400, { ok: false, error: 'obligado_nif_required' });

    const err = (await downloadRepresentationGrantModel(modelFields()).catch(
      (e: unknown) => e,
    )) as RepresentationGrantError;

    expect(err.code).toBe('obligado_nif_required');
    expect(err.statusCode).toBeUndefined();
  });
});

describe('la subida', () => {
  it('manda los ficheros y el tipo de documento como multipart', async () => {
    respondWith(201, { ok: true, status: 'pendiente', at: '2026-08-28T09:00:00Z' });

    const state = await postRepresentationGrant(capture());

    expect(state.status).toBe('pendiente');
    const [, init] = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock
      .calls[0] as [string, RequestInit];
    const form = init.body as FormData;
    expect(form.get('document_type')).toBe('dni');
    expect(form.get('signed_document')).toBeInstanceOf(File);
    expect(form.get('dni_copy')).toBeInstanceOf(File);
    // Lo que no se subió NO viaja como parte vacía.
    expect(form.get('signature_sample')).toBeNull();
    expect(form.get('representation_proof')).toBeNull();
  });

  it('los documentos opcionales viajan cuando los hay', async () => {
    respondWith(201, { ok: true, status: 'pendiente', at: '' });

    await postRepresentationGrant({
      ...capture(),
      document_type: 'nie',
      signature_sample: new File([new Uint8Array([3])], 'firma.jpg', { type: 'image/jpeg' }),
      representation_proof: new File([new Uint8Array([4])], 'escritura.pdf', {
        type: 'application/pdf',
      }),
    });

    const [, init] = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock
      .calls[0] as [string, RequestInit];
    const form = init.body as FormData;
    expect(form.get('signature_sample')).toBeInstanceOf(File);
    expect(form.get('representation_proof')).toBeInstanceOf(File);
  });

  it('🔴 el motivo del rechazo llega ENTERO: la pantalla lo traduce por código', async () => {
    respondWith(400, { ok: false, error: 'signature_sample_required' });

    const err = (await postRepresentationGrant(capture()).catch(
      (e: unknown) => e,
    )) as RepresentationGrantError;

    expect(err).toBeInstanceOf(RepresentationGrantError);
    expect(err.code).toBe('signature_sample_required');
  });
});

describe('el estado', () => {
  it('trae el motivo del rechazo, que es lo único accionable de un «rechazado»', async () => {
    respondWith(200, {
      ok: true,
      status: 'rechazado',
      at: '2026-08-29T10:00:00Z',
      rejected_reason: 'La copia del DNI está ilegible.',
      signature_kind: 'handwritten',
      document_type: 'dni',
    });

    const state = await getRepresentationGrant();

    expect(state.status).toBe('rechazado');
    expect(state.rejected_reason).toContain('ilegible');
  });
});
