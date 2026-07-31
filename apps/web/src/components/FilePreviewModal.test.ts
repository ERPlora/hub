// @vitest-environment happy-dom
// Contrato del visor de ficheros de `/files` (ADR-0165): un modal GRANDE que previsualiza dentro
// del Hub en vez de escupir el fichero a una pestaña del navegador.
//   - Los bytes SIEMPRE salen del runtime (sesión del hub); el navegador no toca disco ni S3.
//   - Cada tipo tiene su visor; los parsers pesados (pdf/xlsx/docx) se cargan PEREZOSAMENTE,
//     así que abrir un .txt no descarga un megabyte de pdf.js.
//   - Lo que no se sabe pintar lo dice claramente y ofrece descargar: nunca un modal en blanco.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchMediaBytes = vi.fn();
vi.mock('../lib/media', () => ({ fetchMediaBytes: (...a: unknown[]) => fetchMediaBytes(...a) }));

const loadSheet = vi.fn();
const loadDocx = vi.fn();
const renderPdf = vi.fn();
vi.mock('../lib/file-preview-loaders', () => ({
  loadSheet: (...a: unknown[]) => loadSheet(...a),
  loadDocx: (...a: unknown[]) => loadDocx(...a),
  renderPdf: (...a: unknown[]) => renderPdf(...a),
}));

// HubIcon hornea los SVG vía `~icons/…?raw`, que el entorno de test deniega (igual que en
// ImportPanel.test.ts). Aquí se prueba el contrato del visor, no los iconos.
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import FilePreviewModal from './FilePreviewModal.vue';
import type { MediaFile } from '../lib/media';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

const bytesOf = (text: string): ArrayBuffer => new TextEncoder().encode(text).buffer;

function mountModal(file: MediaFile | null, open = true): VueWrapper {
  return mount(FilePreviewModal, {
    props: { file, open },
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
}

beforeEach(() => {
  fetchMediaBytes.mockReset().mockResolvedValue(bytesOf('hola'));
  loadSheet.mockReset();
  loadDocx.mockReset();
  renderPdf.mockReset();
  // happy-dom no trae object URLs.
  URL.createObjectURL = vi.fn(() => 'blob:preview');
  URL.revokeObjectURL = vi.fn();
});

describe('FilePreviewModal', () => {
  it('no pide los bytes mientras está cerrado', async () => {
    mountModal({ id: 'a.txt', name: 'a.txt', url: '/api/media/raw?path=a.txt' }, false);
    await flushPromises();
    expect(fetchMediaBytes).not.toHaveBeenCalled();
  });

  it('pide los bytes al runtime, no a S3 ni al disco', async () => {
    const file = { id: 'f/a.txt', name: 'a.txt', url: '/api/media/raw?path=f%2Fa.txt' };
    mountModal(file);
    await flushPromises();
    expect(fetchMediaBytes).toHaveBeenCalledWith(file);
  });

  it('muestra el texto decodificado de un log en el visor de código', async () => {
    fetchMediaBytes.mockResolvedValue(bytesOf('INFO arrancado'));
    const wrapper = mountModal({ id: 'hub.log', name: 'hub.log' });
    await flushPromises();
    const code = wrapper.find('ok-code');
    expect(code.exists()).toBe(true);
    expect((code.element as HTMLElement & { code: string }).code).toBe('INFO arrancado');
  });

  it('usa el visor plegable para JSON', async () => {
    fetchMediaBytes.mockResolvedValue(bytesOf('{"id":"pos"}'));
    const wrapper = mountModal({ id: 'module.json', name: 'module.json' });
    await flushPromises();
    const viewer = wrapper.find('ok-json-viewer');
    expect(viewer.exists()).toBe(true);
    expect((viewer.element as HTMLElement & { data: unknown }).data).toEqual({ id: 'pos' });
  });

  it('pinta una imagen desde un object URL y lo revoca al cerrar (sin fugas)', async () => {
    const wrapper = mountModal({ id: 'logo.png', name: 'logo.png' });
    await flushPromises();
    expect(wrapper.find('img.preview-image').attributes('src')).toBe('blob:preview');
    await wrapper.setProps({ open: false });
    await flushPromises();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview');
  });

  it('convierte la hoja de cálculo en tabla y ofrece sus pestañas de hoja', async () => {
    loadSheet.mockResolvedValue({
      sheets: [
        { name: 'Enero', rows: [['ref', 'total'], ['A-1', '14,52']] },
        { name: 'Febrero', rows: [['ref', 'total']] },
      ],
    });
    const wrapper = mountModal({ id: 'ventas.xlsx', name: 'ventas.xlsx' });
    await flushPromises();
    expect(loadSheet).toHaveBeenCalled();
    const table = wrapper.find('ok-data-table');
    expect(table.exists()).toBe(true);
    // La primera fila del fichero es la cabecera de la tabla.
    const columns = (table.element as HTMLElement & { columns: { key: string }[] }).columns;
    expect(columns.map((c) => c.key)).toEqual(['c0', 'c1']);
    expect(wrapper.text()).toContain('Enero');
    expect(wrapper.text()).toContain('Febrero');
  });

  it('convierte el .docx a HTML y lo pinta saneado', async () => {
    loadDocx.mockResolvedValue('<h1>Presupuesto</h1><p>Total 1.200 €</p>');
    const wrapper = mountModal({ id: 'p.docx', name: 'p.docx' });
    await flushPromises();
    expect(loadDocx).toHaveBeenCalled();
    expect(wrapper.find('.preview-document').html()).toContain('<h1>Presupuesto</h1>');
  });

  it('no carga pdf.js para abrir un fichero de texto (carga perezosa de verdad)', async () => {
    mountModal({ id: 'a.txt', name: 'a.txt' });
    await flushPromises();
    expect(renderPdf).not.toHaveBeenCalled();
    expect(loadSheet).not.toHaveBeenCalled();
    expect(loadDocx).not.toHaveBeenCalled();
  });

  it('dice que no puede previsualizar un .zip y ni siquiera lo descarga', async () => {
    const wrapper = mountModal({ id: 'backup.zip', name: 'backup.zip' });
    await flushPromises();
    expect(fetchMediaBytes).not.toHaveBeenCalled();
    expect(wrapper.find('.preview-unsupported').exists()).toBe(true);
  });

  it('avisa cuando los bytes no llegan, en vez de dejar el modal en blanco', async () => {
    fetchMediaBytes.mockResolvedValue(null);
    const wrapper = mountModal({ id: 'a.txt', name: 'a.txt' });
    await flushPromises();
    expect(wrapper.find('.preview-error').exists()).toBe(true);
  });

  it('deja descargar el fichero desde el propio modal y cerrarlo', async () => {
    const wrapper = mountModal({ id: 'a.txt', name: 'a.txt' });
    await flushPromises();
    await wrapper.find('[data-test="preview-download"]').trigger('click');
    await wrapper.find('[data-test="preview-close"]').trigger('click');
    expect(wrapper.emitted('download')).toHaveLength(1);
    expect(wrapper.emitted('close')).toHaveLength(1);
  });

  it('descarta los bytes de un fichero que ya no se está viendo (respuesta que llega tarde)', async () => {
    // Abres un .log grande, no esperas y abres otro: la respuesta lenta del primero no debe
    // pisar el contenido del segundo.
    let resolveSlow: (v: ArrayBuffer) => void = () => {};
    fetchMediaBytes.mockImplementationOnce(
      () => new Promise<ArrayBuffer>((resolve) => (resolveSlow = resolve)),
    );
    const wrapper = mountModal({ id: 'lento.log', name: 'lento.log' });
    fetchMediaBytes.mockResolvedValue(bytesOf('el rápido'));
    await wrapper.setProps({ file: { id: 'rapido.log', name: 'rapido.log' } });
    await flushPromises();
    resolveSlow(bytesOf('el lento'));
    await flushPromises();
    expect((wrapper.find('ok-code').element as HTMLElement & { code: string }).code).toBe('el rápido');
  });
});
