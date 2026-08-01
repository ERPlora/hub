// @vitest-environment happy-dom
// Contrato del editor de páginas públicas (ADR-0160 F2). PageEditor envuelve Editor.js y produce
// JSON de bloques (NO HTML). Aquí probamos el CONTRATO del wrapper, no la librería: Editor.js y sus
// tools se mockean (tocan el DOM real y no hacen falta para verificar el cableado).
//
// Contrato bajo prueba:
//   - monta sin error y crea UNA instancia de Editor.js sobre su holder;
//   - registra SOLO los tools curados (header, list, quote, delimiter, table, image) y NUNCA los
//     peligrosos (`raw` = HTML crudo, `embed` = iframes) — decisión de seguridad de ADR-0160;
//   - el tool `image` va con un `uploader` propio (media del Hub /files, ADR-0047), no un endpoint
//     externo;
//   - `initialData` se pasa como `data` al editor;
//   - `save()` devuelve el JSON del editor y además lo emite en `@save`;
//   - al desmontar, llama a `editor.destroy()` (limpieza).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import type { OutputData } from '@editorjs/editorjs';

// Instancia mock de Editor.js compartida entre el mock del módulo y las aserciones (vi.hoisted
// para poder referenciarla desde la factory de vi.mock, que se iza por encima de los imports).
const { EditorMock, instances, SAVE_RESULT } = vi.hoisted(() => {
  const instances: Array<{ config: Record<string, unknown>; save: ReturnType<typeof vi.fn>; destroy: ReturnType<typeof vi.fn> }> = [];
  const SAVE_RESULT = {
    time: 1_700_000_000_000,
    blocks: [{ type: 'paragraph', data: { text: 'hello' } }],
    version: '2.30.0',
  };
  class EditorMock {
    config: Record<string, unknown>;
    isReady = Promise.resolve();
    save = vi.fn().mockResolvedValue(SAVE_RESULT);
    destroy = vi.fn();
    constructor(config: Record<string, unknown>) {
      this.config = config;
      instances.push(this);
    }
  }
  return { EditorMock, instances, SAVE_RESULT };
});

vi.mock('@editorjs/editorjs', () => ({ default: EditorMock }));
// Cada tool curado → una clase sentinela distinta para poder afirmar identidad en la config.
vi.mock('@editorjs/header', () => ({ default: class HeaderTool {} }));
vi.mock('@editorjs/list', () => ({ default: class ListTool {} }));
vi.mock('@editorjs/quote', () => ({ default: class QuoteTool {} }));
vi.mock('@editorjs/delimiter', () => ({ default: class DelimiterTool {} }));
vi.mock('@editorjs/table', () => ({ default: class TableTool {} }));
vi.mock('@editorjs/image', () => ({ default: class ImageTool {} }));
// El wrapper importa el cliente del runtime solo para el uploader de media; lo stubeamos para
// aislar el contrato del editor de la red/entorno del hub.
vi.mock('../lib/runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));

import PageEditor from './PageEditor.vue';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: { pageEditor: { placeholder: 'Write here…' } } },
});

function mountEditor(initialData?: OutputData) {
  return mount(PageEditor, {
    props: initialData === undefined ? {} : { initialData },
    global: { plugins: [i18n] },
  });
}

// Un tool en Editor.js puede ser la clase directamente o `{ class, config }`. Normaliza a la clase.
function toolClass(entry: unknown): unknown {
  return typeof entry === 'function' ? entry : (entry as { class?: unknown }).class;
}

beforeEach(() => {
  instances.length = 0;
});

describe('PageEditor', () => {
  it('monta sin error e instancia Editor.js una sola vez sobre un holder', () => {
    const w = mountEditor();
    expect(w.exists()).toBe(true);
    expect(instances).toHaveLength(1);
    expect(instances[0].config.holder).toBeTruthy();
  });

  it('registra SOLO los tools curados y NUNCA raw ni embed', () => {
    mountEditor();
    const tools = instances[0].config.tools as Record<string, unknown>;
    expect(Object.keys(tools).sort()).toEqual(
      ['delimiter', 'header', 'image', 'list', 'quote', 'table'].sort(),
    );
    // Ninguna clave peligrosa: HTML crudo ni iframes embebidos.
    expect(tools).not.toHaveProperty('raw');
    expect(tools).not.toHaveProperty('embed');
  });

  it('mapea cada tool curado a su clase (no otra librería)', async () => {
    const [{ default: Header }, { default: List }, { default: Quote }, { default: Delimiter }, { default: Table }, { default: Image }] =
      await Promise.all([
        import('@editorjs/header'),
        import('@editorjs/list'),
        import('@editorjs/quote'),
        import('@editorjs/delimiter'),
        import('@editorjs/table'),
        import('@editorjs/image'),
      ]);
    mountEditor();
    const tools = instances[0].config.tools as Record<string, unknown>;
    expect(toolClass(tools.header)).toBe(Header);
    expect(toolClass(tools.list)).toBe(List);
    expect(toolClass(tools.quote)).toBe(Quote);
    expect(toolClass(tools.delimiter)).toBe(Delimiter);
    expect(toolClass(tools.table)).toBe(Table);
    expect(toolClass(tools.image)).toBe(Image);
  });

  it('configura el tool image con un uploader propio (media del Hub, no endpoint externo)', () => {
    mountEditor();
    const tools = instances[0].config.tools as Record<string, { config?: { uploader?: { uploadByFile?: unknown }; endpoints?: unknown } }>;
    const image = tools.image;
    expect(image.config?.uploader?.uploadByFile).toBeTypeOf('function');
    // No debe delegar en un endpoint remoto: el subir lo controla nuestro uploader.
    expect(image.config?.endpoints).toBeUndefined();
  });

  it('el uploader solo acepta el namespace público /files/pages', async () => {
    mountEditor();
    const tools = instances[0].config.tools as Record<string, {
      config?: { uploader?: { uploadByUrl?: (url: string) => Promise<{ success: number }> } };
    }>;
    const uploadByUrl = tools.image.config?.uploader?.uploadByUrl;
    expect(uploadByUrl).toBeTypeOf('function');
    await expect(uploadByUrl!('/files/pages/carta/plato.png')).resolves.toMatchObject({ success: 1 });
    await expect(uploadByUrl!('/files/contracts/private.pdf')).resolves.toMatchObject({ success: 0 });
    await expect(uploadByUrl!('https://evil.test/image.png')).resolves.toMatchObject({ success: 0 });
  });

  it('pasa initialData como `data` al editor', () => {
    const data = { time: 42, blocks: [{ type: 'header', data: { text: 'Hi', level: 2 } }], version: '2.30.0' };
    mountEditor(data);
    expect(instances[0].config.data).toEqual(data);
  });

  it('save() devuelve el JSON del editor y lo emite en @save', async () => {
    const w = mountEditor();
    const returned = await (w.vm as unknown as { save: () => Promise<unknown> }).save();
    expect(returned).toEqual(SAVE_RESULT);
    expect(w.emitted('save')).toBeTruthy();
    expect(w.emitted('save')![0][0]).toEqual(SAVE_RESULT);
  });

  it('destruye el editor al desmontar', () => {
    const w = mountEditor();
    const instance = instances[0];
    w.unmount();
    expect(instance.destroy).toHaveBeenCalledTimes(1);
  });
});
