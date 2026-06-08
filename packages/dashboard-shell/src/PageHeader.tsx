// Cabecera de página: navegación (menú/atrás) + acciones globales inyectadas por el shell.
// Las acciones llegan por contexto (las inyecta el consumidor en <DashboardShell>); aquí
// sólo aportamos el patrón responsive: las `pinned` siempre visibles, el resto colapsa en
// un menú overflow en móvil.
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
import { LuEllipsisVertical } from 'react-icons/lu';
import { useShellChrome } from './context';

interface PageHeaderProps {
  title: string;
  backHref?: string;
}

export function PageHeader({ title, backHref }: PageHeaderProps) {
  const { headerActions } = useShellChrome();
  const pinned = headerActions.filter((a) => a.pinned);
  const collapsible = headerActions.filter((a) => !a.pinned);

  return (
    <IonHeader>
      <IonToolbar className="ion-no-border">
        <IonButtons slot="start">
          {/* Patrón Ionic: página raíz → menú; página secundaria → atrás. Nunca ambos. */}
          {backHref ? <IonBackButton defaultHref={backHref} /> : <IonMenuButton />}
        </IonButtons>
        <IonTitle>{title}</IonTitle>
        <IonButtons slot="end">
          {/* Acciones fijas (time-sensitive, p. ej. notificaciones): siempre visibles. */}
          {pinned.map((a) => (
            <IonButton key={a.id} aria-label={a.label} onClick={a.onClick}>
              <a.Icon size={20} />
            </IonButton>
          ))}

          {/* Acciones secundarias: visibles solo en desktop (>= sm). */}
          {collapsible.map((a) => (
            <IonButton
              key={a.id}
              className="hidden sm:inline-flex"
              aria-label={a.label}
              onClick={a.onClick}
            >
              <a.Icon size={20} />
            </IonButton>
          ))}

          {/* En mobile (< sm) las secundarias colapsan en un menú overflow. */}
          {collapsible.length > 0 && (
            <IonButton
              id="erplora-header-overflow"
              className="inline-flex sm:hidden"
              aria-label="Más opciones"
            >
              <LuEllipsisVertical size={20} />
            </IonButton>
          )}
        </IonButtons>

        {collapsible.length > 0 && (
          <IonPopover
            trigger="erplora-header-overflow"
            dismissOnSelect
            className="erplora-overflow-popover"
          >
            <IonList lines="none">
              {collapsible.map((a) => (
                <IonItem key={a.id} button detail={false} onClick={a.onClick}>
                  <span slot="start" className="inline-flex">
                    <a.Icon size={18} />
                  </span>
                  <IonLabel>{a.label}</IonLabel>
                </IonItem>
              ))}
            </IonList>
          </IonPopover>
        )}
      </IonToolbar>
    </IonHeader>
  );
}
