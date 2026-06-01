// Contenido de Roles como pestaña reutilizable (sin IonPage/Header): vive dentro
// de Empleados como último tab. Usa el DataTable central (lista + tarjetas).
import { useState } from 'react';
import { IonButton } from '@ionic/react';
import { LuUsers, LuPencil, LuTrash2 } from 'react-icons/lu';
import { DataTable, type DataTableColumn } from '../components/DataTable';
import { Badge } from '../components/Badge';

interface Role {
  id: string;
  name: string;
  scope: 'Sistema' | 'Personalizado';
  members: number;
  permissions: number;
  createdAt: string; // ISO
}

const BASE_ROLES: Role[] = [
  { id: 'admin', name: 'Administrador', scope: 'Sistema', members: 1, permissions: 48, createdAt: '2025-01-12' },
  { id: 'manager', name: 'Encargado', scope: 'Sistema', members: 2, permissions: 31, createdAt: '2025-01-12' },
  { id: 'cashier', name: 'Cajero', scope: 'Personalizado', members: 4, permissions: 9, createdAt: '2025-03-04' },
  { id: 'stock', name: 'Almacén', scope: 'Personalizado', members: 1, permissions: 12, createdAt: '2025-04-21' },
  { id: 'waiter', name: 'Camarero', scope: 'Personalizado', members: 6, permissions: 7, createdAt: '2025-05-18' },
  { id: 'kitchen', name: 'Cocina', scope: 'Personalizado', members: 3, permissions: 5, createdAt: '2025-02-09' },
  { id: 'host', name: 'Recepción', scope: 'Personalizado', members: 2, permissions: 6, createdAt: '2025-03-22' },
  { id: 'accountant', name: 'Contabilidad', scope: 'Sistema', members: 1, permissions: 22, createdAt: '2025-01-30' },
  { id: 'buyer', name: 'Compras', scope: 'Personalizado', members: 2, permissions: 14, createdAt: '2025-04-02' },
  { id: 'marketing', name: 'Marketing', scope: 'Personalizado', members: 1, permissions: 8, createdAt: '2025-05-05' },
  { id: 'support', name: 'Soporte', scope: 'Personalizado', members: 3, permissions: 11, createdAt: '2025-02-18' },
  { id: 'auditor', name: 'Auditor', scope: 'Sistema', members: 1, permissions: 19, createdAt: '2025-01-22' },
];

// Dataset mayor (demo) para ver la paginación real en el footer.
const ROLES: Role[] = Array.from({ length: 58 }, (_, i) => {
  const base = BASE_ROLES[i % BASE_ROLES.length];
  return i < BASE_ROLES.length
    ? base
    : { ...base, id: `${base.id}-${i}`, name: `${base.name} ${Math.floor(i / BASE_ROLES.length) + 1}` };
});

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });

// Todas las columnas son ordenables por defecto. "Rol" sin width → flexible.
const ROLE_COLUMNS: Array<DataTableColumn<Role>> = [
  { key: 'name', header: 'Rol' },
  {
    key: 'scope', header: 'Ámbito', filter: 'select', width: '9rem',
    cell: (r) => <Badge tone={r.scope === 'Sistema' ? 'primary' : 'neutral'}>{r.scope}</Badge>,
  },
  { key: 'members', header: 'Miembros', align: 'center', width: '6.5rem' },
  { key: 'permissions', header: 'Permisos', align: 'center', width: '6.5rem' },
  { key: 'createdAt', header: 'Creado', filter: 'dateRange', width: '8.5rem', cell: (r) => fmtDate(r.createdAt) },
];

export function RolesTab() {
  const [rows] = useState<Role[]>(ROLES);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  return (
    <div className="flex h-full flex-col">
      <DataTable
        columns={ROLE_COLUMNS}
        rows={rows}
        rowKey={(r) => r.id}
        title="Roles"
        selectable
        selectedKeys={selected}
        onSelectionChange={setSelected}
        pageSize={12}
        enableExport
        enableImport
        exportFilename="roles"
        onImport={(imported) => console.info('CSV importado', imported)}
        primaryAction={{ label: 'Nuevo rol', onClick: () => {} }}
        rowActions={(r) => (
          <>
            <IonButton fill="clear" size="small" aria-label={`Editar ${r.name}`} onClick={() => console.info('editar', r.id)}>
              <LuPencil size={17} />
            </IonButton>
            <IonButton fill="clear" size="small" color="danger" aria-label={`Borrar ${r.name}`} onClick={() => console.info('borrar', r.id)}>
              <LuTrash2 size={17} />
            </IonButton>
          </>
        )}
        cardIcon={() => <LuUsers size={18} />}
        cardTitle={(r) => r.name}
        renderCard={(r) => (
          <div className="flex flex-col gap-2 p-4">
            <div><Badge tone={r.scope === 'Sistema' ? 'primary' : 'neutral'}>{r.scope}</Badge></div>
            <div className="mt-1 flex gap-2">
              <Badge>{r.members} miembros</Badge>
              <Badge tone="primary">{r.permissions} permisos</Badge>
            </div>
            <span className="text-xs text-[color:var(--ion-color-medium)]">Creado {fmtDate(r.createdAt)}</span>
          </div>
        )}
      />
    </div>
  );
}
