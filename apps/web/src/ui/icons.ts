// Iconos vía react-icons (https://react-icons.github.io/react-icons/). Usamos el set
// Lucide (`lu`) por defecto, pero al venir de react-icons tenemos TODOS los packs
// disponibles (fa, md, hi, tb, bi, …) importando desde su subruta correspondiente.
//
// Reexportamos aquí los que usa la app para tener un punto único; cualquier vista puede
// además importar directamente de 'react-icons/<pack>' lo que necesite.
export {
  LuLayoutDashboard,
  LuUsers,
  LuFileText,
  LuStore,
  LuPackage,
  LuCpu,
  LuSettings,
  LuBell,
  LuSparkles,
  LuSun,
  LuMoon,
  LuLogIn,
  LuLogOut,
  LuUserPlus,
  LuSearch,
  LuTrendingUp,
  LuReceipt,
  LuCalculator,
  LuMonitor,
  LuCreditCard,
  LuRefreshCw,
  LuPackagePlus,
  LuLockOpen,
  LuDelete,
} from 'react-icons/lu';

export type { IconType } from 'react-icons';
