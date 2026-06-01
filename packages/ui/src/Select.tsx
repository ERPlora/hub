import { useState } from 'react';
import { cx } from './lib/cx';
import { Icon } from './Icon';
import { useClickAway } from './lib/useClickAway';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  icon?: string;
  width?: number | string;
}

export function Select({ value, onChange, options, placeholder = 'Todos', icon, width }: SelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useClickAway<HTMLDivElement>(() => setOpen(false));
  const current = options.find((o) => o.value === value);
  return (
    <div className="relative" ref={ref} style={{ width }}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="ctl ring-focus flex h-11 w-full items-center gap-2 rounded-[var(--r-ctl)] pl-3 pr-2.5 text-[14px] font-medium transition"
        style={{ color: current ? 'var(--ink)' : 'var(--muted)' }}
      >
        {icon && <Icon name={icon} size={16} style={{ color: 'var(--muted)' }} />}
        <span className="flex-1 truncate text-left">{current ? current.label : placeholder}</span>
        <Icon name="chevron-down" size={16} className={cx('transition', open && 'rotate-180')} style={{ color: 'var(--muted)' }} />
      </button>
      {open && (
        <div className="pop-in absolute z-40 mt-2 max-h-72 w-full overflow-auto rounded-[14px] border p-1.5 shadow-xl" style={{ background: 'var(--surface)', borderColor: 'var(--line)' }}>
          {options.map((o) => {
            const sel = o.value === value;
            return (
              <button
                key={o.value}
                onClick={() => { onChange(o.value); setOpen(false); }}
                className="flex w-full items-center gap-2 rounded-[9px] px-2.5 py-2 text-left text-[13.5px] font-medium transition hover:bg-[var(--surface-2)]"
                style={{ color: 'var(--ink)', background: sel ? 'var(--brand-soft)' : 'transparent' }}
              >
                <span className="flex-1 truncate">{o.label}</span>
                {sel && <Icon name="check" size={15} style={{ color: 'var(--brand)' }} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
