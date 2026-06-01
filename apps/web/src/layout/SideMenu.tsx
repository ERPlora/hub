// Menú lateral con componentes Ionic reales + react-icons + utilidades Tailwind.
import {
  IonMenu, IonHeader, IonToolbar, IonContent, IonList, IonItem, IonLabel,
  IonListHeader, IonMenuToggle, IonFooter, IonSegment, IonSegmentButton, IonActionSheet,
} from '@ionic/react';
import { useRef } from 'react';
import { useLocation, useHistory } from 'react-router-dom';
import { cameraOutline, trashOutline, settingsOutline, logOutOutline } from 'ionicons/icons';
import { Logo } from '../ui/Logo';
import { Avatar } from '../ui/Avatar';
import { useAuth } from '../lib/auth';
import { useLocalAvatar, fileToAvatarDataUrl } from '../lib/localAvatar';
import { NAV } from './nav';

export function SideMenu() {
  const location = useLocation();
  const history = useHistory();
  const { user, logout } = useAuth();
  const [localAvatar, setLocalAvatar] = useLocalAvatar(user?.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLIonMenuElement>(null);

  // La foto LOCAL (de este dispositivo) tiene preferencia; si no, la del Cloud.
  const avatarSrc = localAvatar ?? user?.avatarUrl ?? null;

  const onPickFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // permite re-elegir el mismo archivo
    if (!file) return;
    try {
      setLocalAvatar(await fileToAvatarDataUrl(file));
    } catch {
      // Imagen no procesable: no rompemos la UI, se mantiene el avatar actual.
    }
  };

  return (
    <IonMenu ref={menuRef} contentId="main" type="overlay">
      <IonHeader className="ion-no-border">
        <IonToolbar className="ion-no-border">
          <div className="erplora-logo-pad"><Logo size="sm" /></div>
          <div className="px-3 pb-3">
            <IonSegment mode="ios" value="hub">
              <IonSegmentButton value="hub">
                <IonLabel>Hub</IonLabel>
              </IonSegmentButton>
              <IonSegmentButton value="cloud">
                <IonLabel>Cloud</IonLabel>
              </IonSegmentButton>
            </IonSegment>
          </div>
        </IonToolbar>
      </IonHeader>
      <IonContent>
        {NAV.map((section) => (
          <IonList key={section.label} className="erplora-nav-list">
            <IonListHeader>
              <IonLabel className="erplora-section-label">{section.label}</IonLabel>
            </IonListHeader>
            {section.items.map(({ path, label, Icon }) => (
              <IonMenuToggle key={path} autoHide={false}>
                <IonItem
                  routerLink={path}
                  routerDirection="root"
                  detail={false}
                  lines="none"
                  className={[
                    'erplora-nav-item',
                    location.pathname === path ? 'erplora-nav-item-active' : '',
                  ].join(' ')}
                >
                  <span slot="start" className="flex items-center"><Icon size={20} /></span>
                  <IonLabel>{label}</IonLabel>
                </IonItem>
              </IonMenuToggle>
            ))}
          </IonList>
        ))}
      </IonContent>
      <IonFooter className="ion-no-border">
        <IonToolbar className="ion-no-border">
          {/* Identidad + acceso a la cuenta. El boton abre el menú (Ajustes / salir). */}
          <IonItem
            button
            detail={false}
            lines="none"
            className="erplora-nav-item"
            id="erplora-account-trigger"
          >
            <span slot="start">
              <Avatar name={user?.name ?? '?'} src={avatarSrc} />
            </span>
            <IonLabel>
              <h3 className="font-bold">{user?.name}</h3>
              {user?.email && <p className="text-xs opacity-60">{user.email}</p>}
            </IonLabel>
            {/*
            <span slot="end" className="opacity-50"><LuChevronsUpDown size={16} /></span>
            */}
          </IonItem>
        </IonToolbar>

        <IonActionSheet
          trigger="erplora-account-trigger"
          header={user?.name}
          subHeader={user?.email ?? undefined}
          buttons={[
            // Foto LOCAL de este dispositivo (no se sube al Cloud).
            {
              text: localAvatar ? 'Cambiar foto local' : 'Subir foto local',
              icon: cameraOutline,
              handler: () => { fileRef.current?.click(); },
            },
            ...(localAvatar
              ? [{
                  text: 'Quitar foto local',
                  icon: trashOutline,
                  role: 'destructive' as const,
                  handler: () => { setLocalAvatar(null); },
                }]
              : []),
            {
              text: 'Ajustes',
              icon: settingsOutline,
              handler: () => { menuRef.current?.close(); history.push('/settings'); },
            },
            {
              text: 'Cerrar sesión',
              icon: logOutOutline,
              role: 'destructive' as const,
              handler: () => { logout(); },
            },
            { text: 'Cancelar', role: 'cancel' as const },
          ]}
        />

        {/* Input oculto para elegir la foto local. */}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={onPickFile}
        />
      </IonFooter>
    </IonMenu>
  );
}
