// PagePanel — contenedor visual equivalente al shell del DataTable (rounded-2xl + borde +
// sombra + cabecera opcional) para las vistas que NO usan tabla, de modo que todas las
// pantallas compartan el mismo relieve. El IonContent ya aporta el `ion-padding` exterior;
// aquí va el padding interno y los demás cards se colocan dentro.
import type { ReactNode } from 'react';

const BORDER = 'border-[color:var(--ion-color-step-150,#dcdcdc)]';
const CARD = 'bg-[color:var(--ion-card-background,var(--ion-background-color,#fff))]';
const HEADBG = 'bg-[color:var(--ion-color-step-100,#f4f4f5)]';

interface PagePanelProps {
  /** Título de la cabecera del panel (mismo estilo que el header del DataTable). */
  title?: ReactNode;
  /** Acciones alineadas a la derecha de la cabecera. */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Clases extra para el cuerpo (p. ej. cambiar el gap o el padding). */
  bodyClassName?: string;
}

export function PagePanel({
  title, actions, children, className = '', bodyClassName = 'flex flex-col gap-5 p-4',
}: PagePanelProps) {
  return (
    <div className={`flex flex-col overflow-hidden rounded-2xl border shadow-sm ${BORDER} ${CARD} ${className}`}>
      {(title || actions) && (
        <header className={`flex flex-wrap items-center gap-2 border-b px-4 py-3 ${BORDER} ${HEADBG}`}>
          {title && <h2 className="mr-auto text-[15px] font-semibold leading-none">{title}</h2>}
          {actions}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </div>
  );
}
