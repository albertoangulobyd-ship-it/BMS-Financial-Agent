// La columna "Waarom" / "Why": una frase en palabras normales (dos lineas como mucho, la
// entera al pasar el raton), el codigo de la regla pequeno y gris, y cuantas razones mas.
import { fmt, useT } from '@/i18n';
import type { Why } from '@/lib/why';

export function WhyCell({ why }: { why: Why | null }) {
  const { t } = useT();
  if (!why) return <span className='text-muted-foreground'>—</span>;
  return (
    // Al menos 12rem: a 1024 px la frase sigue leyendose y la tabla cabe sin desplazarse.
    <span className='flex min-w-[12rem] flex-col gap-0.5'>
      <span className='line-clamp-2 text-[13px] leading-snug' title={why.text}>
        {why.text}
      </span>
      {(why.rule || why.more > 0) && (
        <span className='text-[11px] text-muted-foreground'>
          {why.rule && <span className='font-mono'>{why.rule}</span>}
          {why.rule && why.more > 0 && ' · '}
          {why.more > 0 && fmt(why.more === 1 ? t.why.moreOne : t.why.more, { n: why.more })}
        </span>
      )}
    </span>
  );
}
