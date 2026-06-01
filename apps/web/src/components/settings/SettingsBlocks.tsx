import type { ReactNode } from 'react';
import {
  IonCard,
  IonCardContent,
  IonItem,
  IonLabel,
  IonList,
  IonSelect,
  IonSelectOption,
  IonToggle,
} from '@ionic/react';
import type { IconType } from 'react-icons';

interface SettingsCardProps {
  children: ReactNode;
  className?: string;
}

export function SettingsCard({ children, className = '' }: SettingsCardProps) {
  return (
    <IonCard className={`settings-card ${className}`}>
      <IonCardContent className="p-0">{children}</IonCardContent>
    </IonCard>
  );
}

interface SettingsSelectRowProps {
  icon: IconType;
  title: string;
  description: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange?: (value: string) => void;
}

export function SettingsSelectRow({ icon: Icon, title, description, value, options, onChange }: SettingsSelectRowProps) {
  return (
    <IonItem lines="none" className="settings-row">
      <span slot="start" className="settings-icon">
        <Icon size={22} />
      </span>
      <div className="settings-row-body">
        <IonLabel>
          <h2 className="settings-title">{title}</h2>
          <p className="settings-description">{description}</p>
        </IonLabel>
        <IonSelect
          interface="popover"
          value={value}
          className="settings-select"
          aria-label={title}
          onIonChange={(event) => onChange?.(String(event.detail.value))}
        >
          {options.map((option) => (
            <IonSelectOption key={option.value} value={option.value}>
              {option.label}
            </IonSelectOption>
          ))}
        </IonSelect>
      </div>
    </IonItem>
  );
}

interface SettingsToggleRowProps {
  icon: IconType;
  title: string;
  description: string;
  checked?: boolean;
}

export function SettingsToggleRow({ icon: Icon, title, description, checked = false }: SettingsToggleRowProps) {
  return (
    <SettingsCard>
      <IonItem lines="none" className="settings-row settings-row-compact">
        <span slot="start" className="settings-icon">
          <Icon size={22} />
        </span>
        <IonLabel>
          <h2 className="settings-title">{title}</h2>
          <p className="settings-description">{description}</p>
        </IonLabel>
        <IonToggle slot="end" checked={checked} />
      </IonItem>
    </SettingsCard>
  );
}

interface SettingsNavigationRowProps {
  icon: IconType;
  title: string;
  description: string;
  status?: string;
}

export function SettingsNavigationRow({ icon: Icon, title, description, status }: SettingsNavigationRowProps) {
  return (
    <SettingsCard>
      <IonItem button detail lines="none" className="settings-row">
        <span slot="start" className="settings-icon">
          <Icon size={22} />
        </span>
        <IonLabel>
          <h2 className="settings-title">{title}</h2>
          <p className="settings-description">{description}</p>
        </IonLabel>
        {status && (
          <span slot="end" className="settings-status">
            {status}
          </span>
        )}
      </IonItem>
    </SettingsCard>
  );
}

export function SettingsList({ children }: { children: ReactNode }) {
  return <IonList className="settings-list">{children}</IonList>;
}
