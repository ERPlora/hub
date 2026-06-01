// Marca ERPlora como SVG inline (sin CSS custom): hub central + 8 módulos. Usa
// currentColor / el primary de Ionic para integrarse con el tema.
const SIZES = { sm: 28, md: 44, lg: 64 } as const;

export function Logo({ size = 'sm', withWordmark = true }: { size?: keyof typeof SIZES; withWordmark?: boolean }) {
  const px = SIZES[size];
  const brand = 'var(--ion-color-primary, #1496d6)';
  const border = 'color-mix(in srgb, var(--ion-color-primary, #1496d6) 22%, transparent)';
  const mods = [
    [6, 6], [30, 6], [54, 6],
    [6, 30], [54, 30],
    [6, 54], [30, 54], [54, 54],
  ];
  return (
    <span className="inline-flex items-center gap-2.5 align-middle">
      <svg width={px} height={px} viewBox="0 0 72 72" fill="none" aria-hidden>
        {mods.map(([x, y], i) => (
          <rect key={i} x={x} y={y} width={12} height={12} rx={2} fill="transparent" stroke={border} strokeWidth={1.4} />
        ))}
        <rect x={24} y={24} width={24} height={24} rx={4} fill={brand} />
      </svg>
      {withWordmark && (
        <span
          className="font-semibold tracking-tight"
          style={{ fontSize: px * 0.5, color: 'var(--ion-text-color, #1c1b17)' }}
        >
          erplora
        </span>
      )}
    </span>
  );
}
