// FolderAnalysisStatus de Aurora (components/ui/folder-analysis-status.tsx, entrega del
// 28-10-2026), tal cual: cuantas facturas nuevas (verde) y repetidas (naranja) hay en la carpeta,
// de la ultima lectura de los PDF. Cambios: (I) los textos del diccionario; (B) delante, la
// prioridad de la empresa cuando pide algo (especificacion D-41: en el sitio de gf-statuses);
// (B) el punto quieto: en Documentos no late nada (paso 17 B2, desviacion 3).
import type { ReactNode } from 'react';
import { fmt, useT } from '@/i18n';
import type { FolderFile } from './glass-folder-cards';
import { Status, StatusIndicator, StatusLabel } from './status';

export function FolderAnalysisStatus({ files, before }: { files: FolderFile[]; before?: ReactNode }) {
  const { t } = useT();
  const f = t.aurora.folder;
  const added = files.filter((x) => x.analysisStatus === 'new').length,
    repeated = files.filter((x) => x.analysisStatus === 'duplicate').length;
  if (!added && !repeated && !before) return null;
  return (
    <>
      {before}
      {added > 0 && (
        <Status status='online' variant='outline' title={fmt(added === 1 ? f.freshTitleOne : f.freshTitle, { n: added })}>
          <StatusIndicator still />
          <StatusLabel>{fmt(added === 1 ? f.freshOne : f.fresh, { n: added })}</StatusLabel>
        </Status>
      )}
      {repeated > 0 && (
        <Status status='degraded' variant='outline' title={fmt(repeated === 1 ? f.repeatedTitleOne : f.repeatedTitle, { n: repeated })}>
          <StatusIndicator still />
          <StatusLabel>{fmt(repeated === 1 ? f.repeatedOne : f.repeated, { n: repeated })}</StatusLabel>
        </Status>
      )}
    </>
  );
}
