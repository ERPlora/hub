// Icono basado en lucide-react (no CDN → CSP-safe). Acepta nombres kebab-case
// (como el prototipo) y los mapea al componente PascalCase de lucide.
import { icons, type LucideProps } from 'lucide-react';

// Aliases amigables → nombres lucide (espejo del prototipo).
const ALIAS: Record<string, string> = {
  edit: 'pencil',
  trash: 'trash-2',
  sort: 'chevrons-up-down',
  'sort-asc': 'chevron-up',
  'sort-desc': 'chevron-down',
  grid: 'layout-grid',
  apps: 'layout-grid',
  more: 'more-horizontal',
  sparkle: 'sparkles',
  logout: 'log-out',
  expand: 'maximize-2',
  chip: 'cpu',
};

function toPascal(kebab: string): string {
  return kebab
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
}

export interface IconProps extends Omit<LucideProps, 'ref'> {
  name: string;
}

export function Icon({ name, size = 18, strokeWidth = 1.9, ...rest }: IconProps) {
  const resolved = ALIAS[name] ?? name;
  const Cmp = icons[toPascal(resolved) as keyof typeof icons];
  if (!Cmp) return null;
  return <Cmp size={size} strokeWidth={strokeWidth} {...rest} />;
}
