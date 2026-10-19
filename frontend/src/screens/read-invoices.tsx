// Facturen lezen (Read invoices): "wat heeft het lezen van pdf's gekost, en hoe start je
// het?". Primero, en palabras normales, que leer un pdf cuesta dinero y que esta app no lo
// puede empezar (no tiene internet, a proposito): se empieza con el acceso directo del
// escritorio, que dice antes lo que costara. Despues cuanto se ha leido y gastado, lo que
// costaria la siguiente factura (de lo medido) y las ultimas pasadas. No hay ningun boton que
// lo lance.
import { Info } from 'lucide-react';
import { DataTable, type Columns } from '@/components/data-table';
import { Fact, FactStrip } from '@/components/fact-strip';
import { PageHeader, Screen } from '@/components/page-header';
import { ErrorState, Loading } from '@/components/states';
import { DateText } from '@/components/values';
import { fmt, useT } from '@/i18n';
import { paths } from '@/lib/api';
import type { ReadingStatus } from '@/lib/api-types';
import { NBSP, formatUsdMicro } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { useLoad } from './use-load';

/** El acceso directo del escritorio que lanza el lector (windows/instalar.ps1). */

type Pass = ReadingStatus['pasadas'][number];

export function ReadInvoicesScreen() {
  const { t } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const [state, retry] = useLoad(
    () => session!.api.get<{ lectura: ReadingStatus }>(paths.reading).then((r) => r.lectura),
    [session, version]
  );
  const nav = t.nav['read-invoices'];
  return (
    <Screen>
      <PageHeader title={nav.label} description={nav.description} />
      {/* Todo al mismo ancho, como Kasstroom e Importeren. */}
      <div className='max-w-4xl'>
        <HowToStart />
        {state.status === 'loading' && <Loading />}
        {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
        {state.status === 'ready' && <ReadingFigures status={state.data} />}
      </div>
    </Screen>
  );
}

function HowToStart() {
  const { t } = useT();
  return (
    <section aria-labelledby='how-to-start' className='mb-8 rounded-md border border-border bg-card px-5 py-4'>
      <h2 id='how-to-start' className='mb-2 flex items-center gap-2 text-[15px] font-semibold'>
        <Info className='h-4 w-4 text-muted-foreground' aria-hidden='true' />
        {t.reading.howTitle}
      </h2>
      <ul className='flex list-disc flex-col gap-1.5 pl-5 text-[13.5px] leading-relaxed'>
        <li>{t.reading.how1}</li>
        <li>{t.reading.how2}</li>
        {/* Sin el nombre del acceso directo ni del .bat (estan en castellano, como la
            instalacion): la app no ensena castellano. */}
        <li>{t.reading.how3}</li>
        <li className='text-[#45423c]'>{t.reading.how4}</li>
      </ul>
    </section>
  );
}

function ReadingFigures({ status: s }: { status: ReadingStatus }) {
  const { t } = useT();
  const est = s.estimacion;
  const columns: Columns<Pass> = [
    // En una tabla, dd-mm-jjjj como en todas (la prosa es para frases y cifras sueltas).
    { key: 'when', header: t.reading.when, cell: (r) => <DateText value={r.hasta} /> },
    { key: 'count', header: t.reading.count, align: 'right', width: '9rem', cell: (r) => <span className='num'>{r.documentos}</span> },
    { key: 'cost', header: t.reading.cost, align: 'right', width: '9rem', cell: (r) => <span className='num'>{formatUsdMicro(r.coste_usd_micro)}</span> },
  ];
  return (
    <div className='flex flex-col gap-8'>
      <div>
        <FactStrip className='mb-2'>
          <Fact label={t.reading.read}>
            <span className='text-[15px] font-semibold'>
              {fmt(s.documentos === 1 ? t.reading.documentsOne : t.reading.documents, { n: s.documentos })}
            </span>
          </Fact>
          <Fact label={t.reading.spent}>
            <span className='num text-[15px] font-semibold'>{formatUsdMicro(s.coste_usd_micro)}</span>
          </Fact>
          <Fact label={t.reading.perDocument} note={t.reading.average}>
            <span className='num text-[15px] font-semibold'>{formatUsdMicro(s.por_documento_usd_micro)}</span>
          </Fact>
          <Fact label={t.reading.next} note={est ? (est.medida ? t.reading.measured : t.reading.notMeasured) : undefined}>
            <span className='num text-[15px] font-semibold'>
              {est
                ? `${formatUsdMicro(est.por_documento_bajo_usd_micro)} – ${formatUsdMicro(est.por_documento_alto_usd_micro).replace(`$${NBSP}`, '')}`
                : '—'}
            </span>
          </Fact>
          <Fact label={t.reading.lastRead}>
            <span className='text-[15px] font-semibold'>
              <DateText value={s.ultima} prose />
            </span>
          </Fact>
        </FactStrip>
        <p className='text-xs text-muted-foreground'>{t.reading.usdNote}</p>
      </div>
      <section aria-labelledby='passes'>
        <h2 id='passes' className='mb-2 text-[15px] font-semibold'>
          {t.reading.passesTitle}
        </h2>
        <DataTable
          columns={columns}
          rows={s.pasadas}
          rowKey={(r) => `${r.desde ?? ''}-${r.hasta ?? ''}-${r.documentos}`}
          caption={t.reading.passesTitle}
          empty={<p className='text-muted-foreground'>{t.reading.none}</p>}
        />
      </section>
    </div>
  );
}
