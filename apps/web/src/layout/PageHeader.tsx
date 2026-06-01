// Cabecera reutilizable: navegación + acciones globales (asistente, notif, apariencia).
import { useState } from 'react';
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonHeader,
  IonItem,
  IonLabel,
  IonList,
  IonMenuButton,
  IonPopover,
  IonTitle,
  IonToolbar,
} from '@ionic/react';
import {
  LuBell,
  LuEllipsisVertical,
  LuGrid2X2,
  LuSparkles,
  LuSun,
  LuMoon,
} from 'react-icons/lu';
import { useTheme } from '../lib/theme';
import { useAssistant } from '../lib/assistant';
import { useAppSwitcher } from '../lib/appswitcher';
import { ThemeModal } from '../components/ThemeModal';

interface PageHeaderProps {
  title: string;
  backHref?: string;
}

export function PageHeader({ title, backHref }: PageHeaderProps) {
  const { dark } = useTheme();
  const { open } = useAssistant();
  const { open: openApps } = useAppSwitcher();
  const [themeOpen, setThemeOpen] = useState(false);
  return (
    <>
      <IonHeader>
        <IonToolbar className="ion-no-border">
          <IonButtons slot="start">
            {/* Patrón Ionic: página raíz → menú; página secundaria → atrás. Nunca ambos. */}
            {backHref ? <IonBackButton defaultHref={backHref} /> : <IonMenuButton />}
          </IonButtons>
          <IonTitle>{title}</IonTitle>
          <IonButtons slot="end">
            {/* Notificaciones: única acción time-sensitive → siempre visible. */}
            <IonButton aria-label="Notificaciones">
              <LuBell size={20} />
            </IonButton>

            {/* Acciones secundarias: visibles solo en desktop (>= sm). */}
            <IonButton className="hidden sm:inline-flex" aria-label="Apps" onClick={openApps}>
              <LuGrid2X2 size={20} />
            </IonButton>
            <IonButton className="hidden sm:inline-flex" aria-label="Apariencia" onClick={() => setThemeOpen(true)}>
              {dark ? <LuSun size={20} /> : <LuMoon size={20} />}
            </IonButton>
            <IonButton className="hidden sm:inline-flex" aria-label="Asistente" onClick={open}>
              <LuSparkles size={20} />
            </IonButton>

            {/* En mobile (< sm) las secundarias colapsan en un menú overflow. */}
            <IonButton
              id="erplora-header-overflow"
              className="inline-flex sm:hidden"
              aria-label="Más opciones"
            >
              <LuEllipsisVertical size={20} />
            </IonButton>
          </IonButtons>

          <IonPopover
            trigger="erplora-header-overflow"
            dismissOnSelect
            className="erplora-overflow-popover"
          >
            <IonList lines="none">
              <IonItem button detail={false} onClick={openApps}>
                <span slot="start" className="inline-flex">
                  <LuGrid2X2 size={18} />
                </span>
                <IonLabel>Apps</IonLabel>
              </IonItem>
              <IonItem button detail={false} onClick={() => setThemeOpen(true)}>
                <span slot="start" className="inline-flex">
                  {dark ? <LuSun size={18} /> : <LuMoon size={18} />}
                </span>
                <IonLabel>Apariencia</IonLabel>
              </IonItem>
              <IonItem button detail={false} onClick={open}>
                <span slot="start" className="inline-flex">
                  <LuSparkles size={18} />
                </span>
                <IonLabel>Asistente</IonLabel>
              </IonItem>
            </IonList>
          </IonPopover>
        </IonToolbar>
      </IonHeader>
      <ThemeModal isOpen={themeOpen} onClose={() => setThemeOpen(false)} />
    </>
  );
}
