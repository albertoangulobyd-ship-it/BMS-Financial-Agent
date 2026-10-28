// Slider06 de Aurora (components/ui/slider-06.tsx, entrega del 28-10-2026): el rango de importe
// con su sombra al pasar el raton y sus marcas. Cambios: (E) euros enteros, de 0 al total mas
// alto redondeado hacia arriba; las cifras sin NumberFlow (no se anade la dependencia: se
// escriben tal cual); (I) los textos del diccionario.
import { useRef, useState } from 'react';
import { Slider as Primitive } from 'radix-ui';
import { X } from 'lucide-react';
import { useT } from '@/i18n';
import { NBSP, groupThousands } from '@/lib/format';

/** "€ 7.500": euros enteros, en notacion neerlandesa. */
export function wholeEuros(value: number): string {
  return `€${NBSP}${groupThousands(String(Math.max(0, Math.round(value))))}`;
}

/** El paso del deslizador: unas 300 posiciones, en una cifra redonda. */
export function sliderStep(max: number): number {
  const raw = Math.max(1, max / 300);
  const power = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * power).find((v) => v >= raw) ?? power * 10;
}

export default function Slider06({ range, max, onRangeChange }: { range: number[]; max: number; onRangeChange: (range: number[]) => void }) {
  const { t } = useT();
  const s = t.aurora.search;
  const MIN = 0,
    MAX = max,
    STEP = sliderStep(max);
  const [preview, setPreview] = useState<number | null>(null),
    ref = useRef<HTMLDivElement>(null),
    [low = MIN, high = MAX] = range,
    toPct = (v: number) => (v / MAX) * 100;
  let left = 0,
    width = 0;
  if (preview !== null) {
    if (preview < low) {
      left = toPct(preview);
      width = toPct(low - preview);
    } else if (preview > high) {
      left = toPct(high);
      width = toPct(preview - high);
    }
  }
  return (
    <div className='amount-range'>
      <div className='amount-heading'>
        <div>
          <span className='filter-label'>{s.amount}</span>
          <div className='amount-values'>
            {wholeEuros(low)}
            <span>—</span>
            {wholeEuros(high)}
          </div>
        </div>
        <button type='button' disabled={low === MIN && high === MAX} onClick={() => onRangeChange([MIN, MAX])} aria-label={s.amountReset}>
          <X size={13} />
        </button>
      </div>
      <div
        ref={ref}
        className='amount-track-wrap'
        onMouseMove={(e) => {
          const rect = ref.current?.getBoundingClientRect();
          if (rect) setPreview(Math.max(MIN, Math.min(MAX, Math.round((((e.clientX - rect.left) / rect.width) * MAX) / STEP) * STEP)));
        }}
        onMouseLeave={() => setPreview(null)}
      >
        <Primitive.Root className='amount-slider' value={range} onValueChange={onRangeChange} min={MIN} max={MAX} step={STEP} minStepsBetweenThumbs={1}>
          <Primitive.Track className='amount-track'>
            <Primitive.Range className='amount-fill' />
          </Primitive.Track>
          <Primitive.Thumb className='amount-thumb' aria-label={s.amountMin} />
          <Primitive.Thumb className='amount-thumb' aria-label={s.amountMax} />
        </Primitive.Root>
        {width > 0 && <span className='amount-ghost' style={{ left: left + '%', width: width + '%' }} />}
      </div>
      <div className='amount-ticks'>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const v = Math.round(MAX * f);
          return <span key={f}>{v === 0 ? `€0` : `${(v / 1000).toLocaleString('nl-NL', { maximumFractionDigits: 1 })}k`}</span>;
        })}
      </div>
    </div>
  );
}
