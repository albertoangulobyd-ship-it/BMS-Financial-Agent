// Procesar (la otra pantalla de trabajo de Root, mientras su paso no trae la pantalla de la
// suricata, especificacion §5): la lectura de facturas de siempre (screens/read-invoices.tsx)
// dentro del marco de una pantalla de trabajo de Aurora (document-workspace.tsx:36): la marca
// arriba a la izquierda, "← Volver a Aurora" arriba a la derecha, las migas (ws-breadcrumbs,
// con "Inicio" delante) y el orbe pequeno de la esquina (SiriWave de 180 px en su caja de
// 96x52), que es adonde vuela el orbe al entrar y de donde sale al volver. Volver al inicio por
// el orbe, "Volver a Aurora", la miga "Inicio", Alt+← o el boton "atras" del raton lleva el
// vuelo inverso.
import { ArrowLeft, ChevronRight } from 'lucide-react';
import { useEffect } from 'react';
import { useT } from '@/i18n';
import { useSession } from '@/lib/session';
import { ReadInvoicesScreen } from '@/screens/read-invoices';
import { BmsLogo } from './logo';
import { SiriWave } from './orb/siri-wave';
import { useAurora } from './root';

export function WorkScreen() {
  const { t } = useT();
  const { session } = useSession();
  const { go } = useAurora();
  const home = () => go({ type: 'home' });

  // Alt+← y el boton "atras" del raton: la salida visible.
  useEffect(() => {
    const back = () => go({ type: 'home' });
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && !e.ctrlKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        back();
      }
    };
    const onMouse = (e: MouseEvent) => {
      if (e.button === 3) {
        e.preventDefault();
        back();
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mouseup', onMouse);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mouseup', onMouse);
    };
  }, [go]);

  // Una sesion que caduca aqui: Root ya pinta la entrada; esta pantalla, que se funde al irse,
  // no pinta nada (lee de la sesion).
  if (!session) return null;
  return (
    <div className='workspace workspace-host'>
      <BmsLogo />
      <a className='ws-home' role='link' tabIndex={0} onClick={home} onKeyDown={(e) => e.key === 'Enter' && home()}>
        <ArrowLeft size={15} /> {t.aurora.work.back}
      </a>
      <div className='host-frame'>
        <nav className='ws-breadcrumbs' aria-label={t.shell.breadcrumbs}>
          <ol>
            <li>
              <a role='link' tabIndex={0} onClick={home} onKeyDown={(e) => e.key === 'Enter' && home()}>
                {t.aurora.work.home}
              </a>
            </li>
            <li>
              <ChevronRight size={12} aria-hidden='true' />
              <span aria-current='page'>{t.areas.process.label}</span>
            </li>
          </ol>
        </nav>
        <div className='ws-heading host-heading'>
          <div>
            <button type='button' className='ws-companion' onClick={home} aria-label={t.aurora.archive.home}>
              <span className='aurora-shared'>
                <SiriWave size={180} renderScale={1} />
              </span>
            </button>
            <p className='ws-eyebrow'>{t.areas.process.label.toLocaleUpperCase()}</p>
          </div>
        </div>
        {/* role=main y no <main>: las hojas de Aurora dan a main la altura y el recorte del inicio. */}
        <div className='host-body' id='contenido' role='main' tabIndex={-1}>
          <ReadInvoicesScreen />
        </div>
      </div>
    </div>
  );
}
