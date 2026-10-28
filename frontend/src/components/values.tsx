// Importes, horas y fechas, siempre en notacion neerlandesa y con cifras alineadas.
// Sin dato se ve una raya con su explicacion para el lector de pantalla: nunca un 0.
import { useT } from '@/i18n';
import { cn } from '@/lib/utils';
import { NO_VALUE, formatDate, formatDateProse } from '@/lib/format';

function Missing() {
  const { t } = useT();
  return (
    <span className='text-muted-foreground' aria-label={t.common.noData}>
      {NO_VALUE}
    </span>
  );
}

export function DateText({
  value,
  prose = false,
  className,
}: {
  value: string | null | undefined;
  /** En una frase ("16 okt 2026") en vez de en tabla ("16-10-2026"). */
  prose?: boolean;
  className?: string;
}) {
  const { t } = useT();
  const text = prose ? formatDateProse(value, t) : formatDate(value);
  if (text === NO_VALUE) return <Missing />;
  return (
    <time dateTime={value?.slice(0, 10)} className={cn(!prose && 'num whitespace-nowrap', className)}>
      {text}
    </time>
  );
}
