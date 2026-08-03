// @vitest-environment happy-dom
// Contrato UI del modal «Reportar un problema» (lo abre el ítem del menú de usuario del sidebar):
//   - Campo de mensaje (ion-textarea) + botones Enviar / Cancelar.
//   - Enviar con mensaje vacío: no llama a reportUserProblem (guard).
//   - Enviar con mensaje: llama reportUserProblem(msg); en éxito → toastSuccess + cierra + limpia.
//   - Fallo del envío: toastError y NO cierra (el usuario puede reintentar).
//   - Cancelar: cierra sin enviar.
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// Espías del feature (la lógica de red se prueba en lib/report-problem.test.ts; aquí solo el
// contrato UI). `vi.hoisted` evita el TDZ: la factory de `vi.mock` se iza por encima de los consts.
const mocks = vi.hoisted(() => ({
  reportUserProblem: vi.fn(),
  closeReportProblem: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('../lib/report-problem', async () => {
  const { ref } = await import('vue');
  return {
    reportProblemOpen: ref(true),
    reportUserProblem: mocks.reportUserProblem,
    closeReportProblem: mocks.closeReportProblem,
  };
});
vi.mock('../lib/toast', () => ({
  toastSuccess: mocks.toastSuccess,
  toastError: mocks.toastError,
}));

import ReportProblemModal from './ReportProblemModal.vue';
import { reportProblemOpen } from '../lib/report-problem';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      reportProblem: {
        title: 'Report a problem',
        hint: 'Tell us what went wrong.',
        placeholder: 'Describe what happened…',
        send: 'Send',
        cancel: 'Cancel',
        success: 'Thanks — your report was sent.',
        error: 'Your report could not be sent.',
      },
    },
  },
});

function mountModal() {
  // shallow: los ion-* se stubean; aquí se prueba el contrato del modal, no Ionic.
  return mount(ReportProblemModal, {
    shallow: true,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  });
}

async function typeMessage(w: VueWrapper, value: string): Promise<void> {
  (w.getComponent('[data-testid="report-message"]') as VueWrapper).vm.$emit(
    'ionInput',
    new CustomEvent('ionInput', { detail: { value } }),
  );
  await w.vm.$nextTick();
}

beforeEach(() => {
  vi.clearAllMocks();
  reportProblemOpen.value = true;
  mocks.reportUserProblem.mockResolvedValue(true);
});

describe('ReportProblemModal', () => {
  it('pinta campo de mensaje + botones Enviar / Cancelar', () => {
    const w = mountModal();
    expect(w.find('[data-testid="report-message"]').exists()).toBe(true);
    expect(w.find('[data-testid="report-send"]').exists()).toBe(true);
    expect(w.find('[data-testid="report-cancel"]').exists()).toBe(true);
  });

  it('Enviar sin mensaje: no llama a reportUserProblem', async () => {
    const w = mountModal();
    await w.find('[data-testid="report-send"]').trigger('click');
    await flushPromises();
    expect(mocks.reportUserProblem).not.toHaveBeenCalled();
  });

  it('Enviar con mensaje: reporta, en éxito → toast + cierra', async () => {
    const w = mountModal();
    await typeMessage(w, 'no imprime el ticket');
    await w.find('[data-testid="report-send"]').trigger('click');
    await flushPromises();
    expect(mocks.reportUserProblem).toHaveBeenCalledWith('no imprime el ticket');
    expect(mocks.toastSuccess).toHaveBeenCalled();
    expect(mocks.closeReportProblem).toHaveBeenCalled();
  });

  it('fallo del envío → toastError y NO cierra', async () => {
    mocks.reportUserProblem.mockResolvedValue(false);
    const w = mountModal();
    await typeMessage(w, 'algo va mal');
    await w.find('[data-testid="report-send"]').trigger('click');
    await flushPromises();
    expect(mocks.toastError).toHaveBeenCalled();
    expect(mocks.closeReportProblem).not.toHaveBeenCalled();
  });

  it('Cancelar cierra sin enviar', async () => {
    const w = mountModal();
    await w.find('[data-testid="report-cancel"]').trigger('click');
    expect(mocks.reportUserProblem).not.toHaveBeenCalled();
    expect(mocks.closeReportProblem).toHaveBeenCalled();
  });
});
