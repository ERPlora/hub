import { describe, expect, it, vi } from 'vitest';
import { SHELL_MENU_ID, runAfterShellMenuCloses } from './shell-menu';

describe('navegación desde el menú principal', () => {
  it('espera al cierre completo del drawer antes de ejecutar la acción', async () => {
    let resolveClose!: (closed: boolean) => void;
    const close = vi.fn(() => new Promise<boolean>((resolve) => {
      resolveClose = resolve;
    }));
    const action = vi.fn();

    const pending = runAfterShellMenuCloses(action, { close });

    expect(close).toHaveBeenCalledWith(SHELL_MENU_ID);
    expect(action).not.toHaveBeenCalled();

    resolveClose(true);
    await pending;

    expect(action).toHaveBeenCalledOnce();
  });

  it('mantiene la acción disponible si Ionic no puede cerrar el menú', async () => {
    const error = new Error('menu unavailable');
    const close = vi.fn().mockRejectedValue(error);
    const action = vi.fn();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await runAfterShellMenuCloses(action, { close });

    expect(action).toHaveBeenCalledOnce();
    expect(warn).toHaveBeenCalledWith('[hub] no se pudo cerrar el menú principal', error);
    warn.mockRestore();
  });
});
