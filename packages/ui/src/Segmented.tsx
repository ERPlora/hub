import { Icon } from './Icon';

export interface SegmentedItem {
  value: string;
  label: string;
  icon?: string;
}

export interface SegmentedProps {
  value: string;
  onChange: (v: string) => void;
  items: SegmentedItem[];
  /** true → muestra solo icono (toggle); false → label. */
  iconOnly?: boolean;
}

export function Segmented({ value, onChange, items, iconOnly }: SegmentedProps) {
  return (
    <div className="ctl inline-flex items-center gap-0.5 rounded-[var(--r-ctl)] p-1">
      {items.map((it) => {
        const active = it.value === value;
        return (
          <button
            key={it.value}
            onClick={() => onChange(it.value)}
            aria-label={it.label}
            title={it.label}
            className="ring-focus inline-flex items-center justify-center gap-1.5 rounded-[8px] px-3 py-1.5 text-[13px] font-semibold transition"
            style={{
              background: active ? 'var(--surface)' : 'transparent',
              color: active ? 'var(--brand)' : 'var(--muted)',
              boxShadow: active ? '0 1px 2px rgba(0,0,0,.08)' : 'none',
            }}
          >
            {it.icon && <Icon name={it.icon} size={16} strokeWidth={2} />}
            {!iconOnly && it.label}
          </button>
        );
      })}
    </div>
  );
}
