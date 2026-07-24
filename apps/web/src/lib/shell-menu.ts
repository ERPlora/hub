import { menuController } from '@ionic/vue';

/** ID estable del menú principal para no depender de cuál considere Ionic «abierto». */
export const SHELL_MENU_ID = 'shell-navigation';

type MenuControllerLike = Pick<typeof menuController, 'close'>;

/**
 * Ejecuta una acción del shell solo después de cerrar el drawer.
 *
 * En escritorio `close()` resuelve inmediatamente porque el menú forma parte del split pane. En
 * móvil espera también a la animación, evitando que la nueva ruta quede oculta bajo el drawer.
 * Si Ionic no puede cerrar el menú, la acción sigue disponible y el fallo queda diagnosticable.
 */
export async function runAfterShellMenuCloses(
  action: () => unknown | Promise<unknown>,
  controller: MenuControllerLike = menuController,
): Promise<void> {
  try {
    await controller.close(SHELL_MENU_ID);
  } catch (error) {
    console.warn('[hub] no se pudo cerrar el menú principal', error);
  }
  await action();
}
