// Modal de apariencia: diálogo centrado y compacto (no full-screen).
// Sin IonContent: en un modal de altura automática IonContent colapsa a 0; usamos
// un div con scroll propio (.erplora-theme-body, ver styles en ionic-theme.css).
import {
  IonModal, IonHeader, IonToolbar, IonTitle, IonButtons, IonButton, IonIcon,
} from '@ionic/react';
import { closeOutline } from 'ionicons/icons';
import { ThemePanel } from './ThemePanel';

export function ThemeModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  return (
    <IonModal isOpen={isOpen} onDidDismiss={onClose} className="erplora-theme-modal">
      <IonHeader>
        <IonToolbar className="ion-no-border">
          <IonTitle>Apariencia</IonTitle>
          <IonButtons slot="end">
            <IonButton onClick={onClose} aria-label="Cerrar">
              <IonIcon icon={closeOutline} slot="icon-only" />
            </IonButton>
          </IonButtons>
        </IonToolbar>
      </IonHeader>
      <div className="erplora-theme-body">
        <ThemePanel />
      </div>
    </IonModal>
  );
}
