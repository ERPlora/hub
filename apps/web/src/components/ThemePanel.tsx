// Panel de configuración de tema: Modo (Auto/Light/Dark) + Accent + Densidad.
// Componentes Ionic (IonList/IonItem/IonSegment/IonToggle). Reutilizable: modal
// del header + aside de Ajustes.
import {
  IonList, IonItem, IonLabel, IonSegment, IonSegmentButton, IonToggle, IonNote,
} from '@ionic/react';
import { useTheme, ACCENTS, type ThemeMode, type ThemeAccent } from '../lib/theme';

const ACCENT_LABELS: Record<ThemeAccent, string> = { blue: 'Blue', orange: 'Orange' };

export function ThemePanel() {
  const { mode, setMode, accent, setAccent, compact, setCompact } = useTheme();
  return (
    <IonList lines="full">
      <IonItem>
        <IonLabel>
          <h3>Modo</h3>
          <IonNote>Claro, oscuro o según el sistema</IonNote>
        </IonLabel>
      </IonItem>
      <IonItem lines="none">
        <IonSegment value={mode} onIonChange={(e) => setMode(e.detail.value as ThemeMode)}>
          <IonSegmentButton value="system"><IonLabel>Auto</IonLabel></IonSegmentButton>
          <IonSegmentButton value="light"><IonLabel>Claro</IonLabel></IonSegmentButton>
          <IonSegmentButton value="dark"><IonLabel>Oscuro</IonLabel></IonSegmentButton>
        </IonSegment>
      </IonItem>

      <IonItem>
        <IonLabel>
          <h3>Color de acento</h3>
          <IonNote>Color primario de la interfaz</IonNote>
        </IonLabel>
      </IonItem>
      <IonItem lines="none">
        <IonSegment value={accent} onIonChange={(e) => setAccent(e.detail.value as ThemeAccent)}>
          {(Object.keys(ACCENTS) as ThemeAccent[]).map((key) => (
            <IonSegmentButton key={key} value={key}>
              <IonLabel>
                <span
                  className="mr-2 inline-block h-3 w-3 rounded-full align-middle"
                  style={{ background: ACCENTS[key].hex }}
                />
                {ACCENT_LABELS[key]}
              </IonLabel>
            </IonSegmentButton>
          ))}
        </IonSegment>
      </IonItem>

      <IonItem lines="none">
        <IonToggle checked={compact} onIonChange={(e) => setCompact(e.detail.checked)}>
          <IonLabel>
            <h3>Modo compacto</h3>
            <IonNote>Reduce el tamaño de texto y controles</IonNote>
          </IonLabel>
        </IonToggle>
      </IonItem>
    </IonList>
  );
}
