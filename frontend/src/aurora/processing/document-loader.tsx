// La escena de la lectura de facturas (paso 16): la tarjeta de Aurora con la suricata llevando
// documentos a la pila. Viene de document-loader.tsx del prototipo, sin el lote de ejemplo
// (DEMO_BATCH) ni el progreso inventado: quien la usa dice cuantos documentos hay (`total`),
// cual se esta leyendo (`stage`, desde 0) y cuando se ha acabado (`done`), y pasa las cifras
// de verdad a la tarjeta (`progress`). Hasta que la lectura real llegue a la app (un paso
// posterior), no se monta en ninguna pantalla.
import { useEffect, useRef } from 'react';
import { useT } from '@/i18n';
import { mountLoader, type LoaderHandle } from './loader-engine';
import { ProcessingCard, type ProcessingProgress } from './processing-card';
import './document-loader.css';

export interface DocumentLoaderProps {
  running: boolean;
  total: number;
  /** El documento que se esta leyendo (desde 0), con su titulo y una frase. */
  stage: { index: number; title: string; subtitle?: string } | null;
  done: boolean;
  progress: ProcessingProgress | null;
  onFinished?: () => void;
}

export function DocumentLoader({ running, total, stage, done, progress, onFinished }: DocumentLoaderProps) {
  const { t } = useT();
  const host = useRef<HTMLDivElement>(null);
  const engine = useRef<LoaderHandle | null>(null);
  const finished = useRef(onFinished);
  finished.current = onFinished;
  const texts = t.aurora.loader;

  useEffect(() => {
    if (!host.current) return;
    const loader = mountLoader(host.current, {
      total,
      texts: { preparing: texts.preparing, ready: texts.ready, readySub: texts.readySub, imagesFailed: texts.imagesFailed },
      onFinished: () => finished.current?.(),
    });
    engine.current = loader;
    return () => {
      loader.dispose();
      engine.current = null;
    };
    // Los textos del cargador son los de su idioma al montarse; un cambio de idioma a mitad
    // de una lectura cambia los titulos siguientes (setStage), no la escena.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [total]);

  useEffect(() => {
    if (running) engine.current?.start();
  }, [running]);

  useEffect(() => {
    if (stage) engine.current?.setStage(stage.index, stage.title, stage.subtitle);
  }, [stage]);

  useEffect(() => {
    if (done) engine.current?.finish();
  }, [done]);

  return (
    <ProcessingCard running={running} progress={progress}>
      <div className='document-loader' ref={host} />
    </ProcessingCard>
  );
}
