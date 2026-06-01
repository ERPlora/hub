// Teclado de PIN con Ionic + Tailwind (sin CSS custom). 4 dígitos por defecto.
import { IonButton } from '@ionic/react';
import { LuDelete } from 'react-icons/lu';

export interface PinPadProps {
  value: string;
  onChange: (next: string) => void;
  length?: number;
  error?: boolean;
  disabled?: boolean;
}

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9'];

export function PinPad({ value, onChange, length = 4, error, disabled }: PinPadProps) {
  const push = (d: string) => { if (!disabled && value.length < length) onChange((value + d).slice(0, length)); };
  const back = () => { if (!disabled) onChange(value.slice(0, -1)); };

  return (
    <div className="flex flex-col items-center gap-6">
      {/* indicadores */}
      <div className="flex gap-3">
        {Array.from({ length }).map((_, i) => {
          const filled = i < value.length;
          return (
            <span
              key={i}
              className="h-3.5 w-3.5 rounded-full transition-colors"
              style={{
                background: error ? 'var(--ion-color-danger)' : filled ? 'var(--ion-color-primary)' : 'transparent',
                border: `2px solid ${error ? 'var(--ion-color-danger)' : filled ? 'var(--ion-color-primary)' : 'var(--ion-border-color)'}`,
              }}
            />
          );
        })}
      </div>

      {/* teclado */}
      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((k) => (
          <IonButton key={k} fill="outline" className="h-16 w-16 text-2xl" disabled={disabled} onClick={() => push(k)}>
            {k}
          </IonButton>
        ))}
        <span />
        <IonButton fill="outline" className="h-16 w-16 text-2xl" disabled={disabled} onClick={() => push('0')}>0</IonButton>
        <IonButton fill="outline" className="h-16 w-16" aria-label="Borrar" disabled={disabled} onClick={back}>
          <LuDelete size={22} />
        </IonButton>
      </div>
    </div>
  );
}
