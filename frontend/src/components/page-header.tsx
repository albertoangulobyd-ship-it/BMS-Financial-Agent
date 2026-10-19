// La cabecera de cada pantalla: su titulo, UNA frase que dice que pregunta contesta y,
// como mucho, una accion principal. Asi cada pantalla se entiende sin leer nada mas.
import { useEffect, type ReactNode } from 'react';
import { useT } from '@/i18n';
import { useSession } from '@/lib/session';

export function PageHeader({
  title,
  description,
  action,
  meta,
}: {
  title: string;
  description: string;
  /** Una sola accion principal (un boton). */
  action?: ReactNode;
  /** Algo pequeno y gris junto al titulo (un codigo de referencia). */
  meta?: ReactNode;
}) {
  const { t } = useT();
  const { session } = useSession();
  const demo = session?.environment === 'demo';

  // El titulo de la ventana dice donde se esta (y si son datos de prueba).
  useEffect(() => {
    document.title = `${demo ? `${t.app.testDataTitle} · ` : ''}${title} · ${t.app.name}`;
  }, [demo, title, t]);

  return (
    <header className='flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pb-5'>
      <div className='min-w-0'>
        <div className='flex items-baseline gap-3'>
          <h1 className='text-[21px] leading-tight font-semibold tracking-[-0.005em]'>{title}</h1>
          {meta && <span className='text-xs text-muted-foreground'>{meta}</span>}
        </div>
        <p className='mt-1 text-muted-foreground'>{description}</p>
      </div>
      {action && <div className='shrink-0'>{action}</div>}
    </header>
  );
}

/** El marco de una pantalla: ancho maximo comodo y aire alrededor. */
export function Screen({ children }: { children: ReactNode }) {
  return <div className='mx-auto w-full max-w-[1240px] px-5 py-6 xl:px-8'>{children}</div>;
}
