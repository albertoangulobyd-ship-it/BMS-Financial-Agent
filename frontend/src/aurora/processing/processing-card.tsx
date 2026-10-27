// La tarjeta de la lectura (paso 16): la de Aurora, monocroma y tranquila, con la escena dentro
// y debajo el avance. Del prototipo cambia: sin "LECTURA SIMULADA · ARCHIVOS DE EJEMPLO" y sin
// cifras propias: el avance (porcentaje y filas) lo da quien la usa, de la lectura de verdad;
// sin avance no se pinta ninguna barra. Los textos, de los diccionarios.
import type { ReactNode } from 'react';
import { useT } from '@/i18n';
import './processing-card.css';

export interface ProcessingProgress {
  /** 0 a 100, de lo leido de verdad. */
  value: number;
  /** Unas lineas de lo que se esta leyendo (nombres de fichero de la persona, como texto). */
  rows: string;
}

export function ProcessingCard({
  running,
  progress,
  children,
}: {
  running: boolean;
  progress: ProcessingProgress | null;
  children: ReactNode;
}) {
  const { t } = useT();
  const texts = t.aurora.processing;
  const value = progress ? Math.max(0, Math.min(100, Math.round(progress.value))) : 0;
  const filled = Math.floor(value / 5);
  return (
    <div className='aurora-root'>
      <section className={'processing-card ' + (running ? 'is-running' : 'is-queued')} aria-label={texts.card}>
        <div className='pc-outline' aria-hidden='true' />
        <div className='pc-texture' aria-hidden='true'>
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i}>{'·  .    :   ·     .  '.repeat(6)}</span>
          ))}
        </div>
        <div className='pc-label' aria-hidden='true'>
          <span>AURORA / {texts.label}</span>
          <span>{running ? texts.running : texts.queued}</span>
        </div>
        <div className='pc-scene'>{children}</div>
        <div className='pc-reading'>
          {running && progress ? (
            <>
              <div
                className='pc-progress'
                role='progressbar'
                aria-label={texts.progress}
                aria-valuenow={value}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <span aria-hidden='true'>
                  [
                  {Array.from({ length: 20 }, (_, i) => (
                    <i key={i} className={i < filled ? 'filled' : ''}>
                      {i < filled ? '▓' : '░'}
                    </i>
                  ))}
                  ]
                </span>
                <b>{value}%</b>
              </div>
              <pre data-proper-name>{progress.rows}</pre>
            </>
          ) : (
            <p>
              {texts.idle}
              <br />
              <span>{texts.idleSub}</span>
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
