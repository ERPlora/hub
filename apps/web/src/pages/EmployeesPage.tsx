import { useState } from 'react';
import { useHistory } from 'react-router-dom';
import { IonButton, IonIcon } from '@ionic/react';
import { peopleOutline, personCircleOutline, shieldCheckmarkOutline } from 'ionicons/icons';
import { LuPencil, LuTrash2, LuUser } from 'react-icons/lu';
import { PageScaffold } from '../components/PageScaffold';
import { PageTabBar, type PageTabBarItem } from '../components/PageTabBar';
import { DataTable, type DataTableColumn } from '../components/DataTable';
import { Badge } from '../components/Badge';
import { RolesTab } from './RolesTab';

interface Employee {
  id: string;
  name: string;
  email: string | null;
  role: string;
  status: 'Activo' | 'Inactivo';
  createdAt: string;
}

type EmployeeTab = 'staff' | 'users' | 'roles';

const EMPLOYEES: Employee[] = [
  { id: '1', name: 'Demo Admin', email: 'demo@erplora.com', role: 'Administrador', status: 'Activo', createdAt: '2025-01-12' },
  { id: '2', name: 'María López', email: 'maria@erplora.com', role: 'Encargado', status: 'Activo', createdAt: '2025-02-03' },
  { id: '3', name: 'Juan Pérez', email: 'juan@erplora.com', role: 'Cajero', status: 'Activo', createdAt: '2025-02-20' },
  { id: '4', name: 'Ana Ruiz', email: 'ana@erplora.com', role: 'Almacén', status: 'Inactivo', createdAt: '2025-03-15' },
  { id: '5', name: 'Luis Gómez', email: 'luis@erplora.com', role: 'Camarero', status: 'Activo', createdAt: '2025-04-09' },
  { id: '6', name: 'Sara Díaz', email: null, role: 'Cocina', status: 'Activo', createdAt: '2025-05-01' },
];

// Roles es el ÚLTIMO tab. La navegación a Roles ya no está en el menú izquierdo.
const tabs: Array<PageTabBarItem<EmployeeTab>> = [
  { value: 'staff', label: 'Staff', icon: <IonIcon icon={peopleOutline} /> },
  { value: 'users', label: 'Usuarios', icon: <IonIcon icon={personCircleOutline} /> },
  { value: 'roles', label: 'Roles', icon: <IonIcon icon={shieldCheckmarkOutline} /> },
];

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });

function Avatar({ name }: { name: string }) {
  return (
    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[color:var(--ion-color-primary)]/15 text-xs font-bold text-[color:var(--ion-color-primary)]">
      {name[0]?.toUpperCase()}
    </span>
  );
}

export function EmployeesPage() {
  const history = useHistory();
  const [tab, setTab] = useState<EmployeeTab>('staff');
  const [rows] = useState<Employee[]>(EMPLOYEES);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const columns: Array<DataTableColumn<Employee>> = [
    {
      key: 'name', header: 'Empleado', width: 'minmax(10rem,1.3fr)',
      cell: (e) => (
        <span className="flex items-center gap-2.5">
          <Avatar name={e.name} />
          <span className="truncate font-medium">{e.name}</span>
        </span>
      ),
    },
    { key: 'email', header: 'Email', width: 'minmax(9rem,1fr)', cell: (e) => e.email ?? '—', value: (e) => e.email ?? '' },
    { key: 'role', header: 'Rol', filter: 'select', width: '8rem' },
    {
      key: 'status', header: 'Estado', filter: 'select', width: '6.5rem',
      cell: (e) => <Badge tone={e.status === 'Activo' ? 'success' : 'neutral'}>{e.status}</Badge>,
    },
    { key: 'createdAt', header: 'Alta', filter: 'dateRange', width: '8rem', cell: (e) => fmtDate(e.createdAt) },
  ];

  return (
    <PageScaffold title="Empleados" footer={<PageTabBar value={tab} items={tabs} onChange={setTab} />}>
      <div className="flex h-full flex-col">
        {tab === 'staff' && (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(e) => e.id}
            title="Staff"
            selectable
            selectedKeys={selected}
            onSelectionChange={setSelected}
            pageSize={12}
            enableExport
            enableImport
            exportFilename="empleados"
            onImport={(imported) => console.info('CSV importado', imported)}
            primaryAction={{ label: 'Nuevo empleado', onClick: () => history.push('/employees/new') }}
            onRowClick={(e) => history.push(`/employees/${e.id}`)}
            rowActions={(e) => (
              <>
                <IonButton fill="clear" size="small" aria-label={`Editar ${e.name}`} onClick={() => history.push(`/employees/${e.id}`)}>
                  <LuPencil size={17} />
                </IonButton>
                <IonButton fill="clear" size="small" color="danger" aria-label={`Borrar ${e.name}`} onClick={() => console.info('borrar', e.id)}>
                  <LuTrash2 size={17} />
                </IonButton>
              </>
            )}
            cardIcon={() => <LuUser size={18} />}
            cardTitle={(e) => e.name}
            renderCard={(e) => (
              <div className="flex flex-col gap-2 p-4">
                <span className="truncate text-sm text-[color:var(--ion-color-medium)]">{e.email ?? '—'}</span>
                <div className="mt-1 flex flex-wrap gap-2">
                  <Badge>{e.role}</Badge>
                  <Badge tone={e.status === 'Activo' ? 'success' : 'neutral'}>{e.status}</Badge>
                </div>
                <span className="text-xs text-[color:var(--ion-color-medium)]">Alta {fmtDate(e.createdAt)}</span>
              </div>
            )}
          />
        )}

        {tab === 'users' && (
          <div className="grid flex-1 place-items-center text-center text-[color:var(--ion-color-medium)]">
            El acceso de usuarios (PIN, cuentas) se gestionará aquí.
          </div>
        )}

        {tab === 'roles' && <RolesTab />}
      </div>
    </PageScaffold>
  );
}

export default EmployeesPage;
