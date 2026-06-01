// Badge de estado/etiqueta — IonBadge nativo con su prop `color` de Ionic + clase
// `glass` (transparencia). Sin clases por-tono: el color lo pone Ionic; .glass usa
// --ion-color-base que Ionic expone según `color`. (IonChip es para filtros pulsables.)
import type { ReactNode } from 'react';
import { IonBadge } from '@ionic/react';

// Tono de la app → color de Ionic.
export type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger';
const ION_COLOR: Record<BadgeTone, string> = {
  neutral: 'medium',
  primary: 'primary',
  success: 'success',
  warning: 'warning',
  danger: 'danger',
};

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: BadgeTone }) {
  return <IonBadge color={ION_COLOR[tone]} className="glass">{children}</IonBadge>;
}
