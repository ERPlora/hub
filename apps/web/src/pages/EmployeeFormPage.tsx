// Alta/edición de empleado (Ionic). Ruta /employees/new y /employees/:id.
import { useState } from 'react';
import { useHistory, useParams } from 'react-router-dom';
import {
  IonCard, IonCardContent, IonList, IonItem, IonInput, IonSelect, IonSelectOption,
  IonToggle, IonButton,
} from '@ionic/react';
import { PageScaffold } from '@erplora/dashboard-shell';
import { useToast } from '../lib/toast';

const ROLES = ['Administrador', 'Encargado', 'Cajero', 'Almacén'];

export function EmployeeFormPage() {
  const { id } = useParams<{ id?: string }>();
  const isEdit = !!id;
  const history = useHistory();
  const { toast } = useToast();
  const [active, setActive] = useState(true);

  return (
    <PageScaffold title={isEdit ? 'Editar empleado' : 'Nuevo empleado'} backHref="/employees">
      <IonCard className="ion-no-margin">
        <IonCardContent>
          <IonList>
            <IonItem><IonInput label="Nombre" labelPlacement="stacked" placeholder="Nombre y apellidos" value={isEdit ? 'María García' : ''} /></IonItem>
            <IonItem><IonInput label="Email" labelPlacement="stacked" type="email" placeholder="empleado@empresa.com" value={isEdit ? 'maria@tienda.com' : ''} /></IonItem>
            <IonItem>
              <IonSelect label="Rol" labelPlacement="stacked" value={isEdit ? 'Encargado' : 'Cajero'}>
                {ROLES.map((r) => <IonSelectOption key={r} value={r}>{r}</IonSelectOption>)}
              </IonSelect>
            </IonItem>
            <IonItem lines="none">
              <IonToggle checked={active} onIonChange={(e) => setActive(e.detail.checked)}>Activo</IonToggle>
            </IonItem>
          </IonList>
          <div className="mt-4 flex justify-end gap-2">
            <IonButton fill="outline" onClick={() => history.push('/employees')}>Cancelar</IonButton>
            <IonButton onClick={() => { toast(isEdit ? 'Empleado actualizado' : 'Empleado creado', { color: 'success' }); history.push('/employees'); }}>
              {isEdit ? 'Guardar' : 'Crear'}
            </IonButton>
          </div>
        </IonCardContent>
      </IonCard>
    </PageScaffold>
  );
}
