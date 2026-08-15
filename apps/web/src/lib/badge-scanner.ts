// **Captura de la placa por TEMPORIZACIÓN, en un listener global del shell** (hub#658).
//
// Un lector RFID/NFC/de banda **es un teclado**: cuando se pasa la tarjeta escribe su número de
// golpe y remata con Enter. La decisión de mercado de la issue lo dice sin matices — la ráfaga se
// captura **por temporización en un listener global, NUNCA por el foco de un campo** — y nombra la
// razón: el foro de Odoo es un registro de diez años de lo que cuesta lo contrario. Si la captura
// depende de que un campo tenga el foco, la ráfaga cae donde esté el cursor (el buscador, una
// cantidad, el nombre de un cliente) y el Enter final «pulsa» el botón que haya debajo del ratón.
// En el mostrador no hay campo que enfocar: nadie hace clic antes de pasar la tarjeta.
//
// La regla, entonces, es sobre la VELOCIDAD:
//
//   · un lector escribe en 1–10 ms por carácter; una persona, en 100 ms o más;
//   · la ráfaga termina en Enter;
//   · lo que va más lento es una persona, y sus pulsaciones tienen que llegar intactas a la página.
//
// Y una consecuencia que importa tanto como la captura: cuando la ráfaga **sí** es una placa, se
// **consume entera** (`preventDefault`), Enter incluido. Ese Enter es exactamente la tecla que
// enviaría el formulario que hubiera abierto.
//
// Este módulo no sabe nada de sesiones ni de aprobaciones: solo dice «alguien acaba de pasar esta
// placa». Quién hace qué con ella lo deciden las pantallas suscritas.

/**
 * Separación máxima entre dos pulsaciones para seguir considerándolas la misma ráfaga.
 *
 * 50 ms es cinco veces lo que tarda el lector más lento entre caracteres y la mitad de lo que tarda
 * una persona rápida entre dos teclas. No es un número que haya que afinar: el hueco entre las dos
 * poblaciones es de un orden de magnitud.
 */
export const BADGE_MAX_GAP_MS = 50;

/**
 * Caracteres mínimos para que una ráfaga sea una placa.
 *
 * Un UID EM4100 son 10 dígitos y el más corto que se ve en catálogo son 4. Por debajo es alguien
 * aporreando Enter o un atajo de dos teclas, y tragarse eso sería romper el teclado de la caja.
 */
const BADGE_MIN_LENGTH = 4;

/** Lo que se hace con una placa recién leída. */
export type BadgeHandler = (badge: string) => void;

/**
 * **Pila** de suscriptores, y la ráfaga va al ÚLTIMO.
 *
 * El diálogo de aprobación se abre encima de una pantalla que también escucha; entregar a los dos
 * aprobaría una acción y abriría una sesión con un solo gesto. El último en suscribirse es el que
 * está delante del usuario, que es justo el criterio que aplica el propio navegador con el foco.
 */
const handlers: BadgeHandler[] = [];

/**
 * Escucha las placas hasta que se llame a la función devuelta.
 *
 * Se llama desde `onMounted` y se desuscribe en `onUnmounted`: una pantalla que se va y deja su
 * handler seguiría recibiendo tarjetas desde debajo de la que la sustituyó.
 */
export function onBadgeScan(handler: BadgeHandler): () => void {
  handlers.push(handler);
  return () => {
    const at = handlers.lastIndexOf(handler);
    if (at !== -1) handlers.splice(at, 1);
  };
}

/** Estado de la ráfaga en curso. Vacío = no hay ninguna. */
let buffer = '';
let lastKeyAt = 0;

/**
 * Instala el listener global. Se llama **una vez**, desde el shell (`App.vue`), y devuelve el
 * desmontaje.
 *
 * Va en fase de **captura** a propósito: tiene que ver la tecla antes que cualquier campo, o el
 * carácter ya habría entrado en el input cuando decidiéramos que era una placa.
 */
export function installBadgeScanner(): () => void {
  const onKeyDown = (ev: KeyboardEvent): void => {
    // Sin nadie escuchando, estas teclas no son nuestras: ni se acumulan ni se tragan. Es lo que
    // hace que el resto del hub siga teniendo un teclado normal cuando no hay placa que esperar.
    if (!handlers.length) return;
    // Un modificador nunca forma parte de un volcado de lector, y un atajo del sistema tampoco:
    // Ctrl+A dentro de una ráfaga es una persona interrumpiendo.
    if (ev.ctrlKey || ev.metaKey || ev.altKey) {
      buffer = '';
      return;
    }

    const now = Date.now();
    const withinBurst = buffer !== '' && now - lastKeyAt <= BADGE_MAX_GAP_MS;
    lastKeyAt = now;

    if (ev.key === 'Enter') {
      const badge = withinBurst ? buffer : '';
      buffer = '';
      if (badge.length < BADGE_MIN_LENGTH) return; // Enter de una persona: que siga su camino.
      // La ráfaga ERA una placa: se consume entera, y este Enter es el que habría enviado el
      // formulario de debajo.
      ev.preventDefault();
      ev.stopPropagation();
      handlers[handlers.length - 1]?.(badge);
      return;
    }

    // Solo el alfabeto que emite un lector. Cualquier otra cosa (F5, Tab, una flecha) rompe la
    // ráfaga en vez de ignorarse: es la señal más fiable de que quien escribe es una persona.
    if (ev.key.length !== 1 || !/[A-Za-z0-9\-_]/.test(ev.key)) {
      buffer = '';
      return;
    }

    buffer = withinBurst ? buffer + ev.key : ev.key;
    // ⚠️ Se traga **desde el primer carácter**, no al confirmar la ráfaga: para cuando supiéramos
    // que es una placa, los diez primeros dígitos ya estarían dentro del buscador. El precio es que
    // una persona escribiendo a más de 20 pulsaciones por segundo perdería teclas — que es el ritmo
    // de una máquina, no el de nadie tecleando.
    if (buffer.length > 1) {
      ev.preventDefault();
      ev.stopPropagation();
    }
  };

  document.addEventListener('keydown', onKeyDown, true);
  return () => {
    document.removeEventListener('keydown', onKeyDown, true);
    buffer = '';
  };
}
