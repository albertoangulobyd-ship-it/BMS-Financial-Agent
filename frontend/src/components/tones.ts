// Que tono lleva cada estado (siempre con su texto al lado: el color ayuda, no dice).
import type { StatusTone } from '@/components/status-text';

export const PAYMENT_TONE: Record<string, StatusTone> = {
  pendiente: 'neutral',
  vencida: 'late',
  pagada: 'ok',
  anulada: 'muted',
  acreditada: 'muted',
};

export const REVIEW_TONE: Record<string, StatusTone> = {
  sin_revisar: 'muted',
  necesita_revision: 'attention',
  revisada: 'ok',
};

export const EXCEPTION_TONE: Record<string, StatusTone> = {
  abierta: 'attention',
  asignada: 'neutral',
  esperando_externo: 'muted',
  resuelta: 'ok',
};

export const FINDING_TONE: Record<string, StatusTone> = {
  abierto: 'attention',
  desaparecido: 'neutral',
  aceptado: 'muted',
  cerrado: 'ok',
  resuelto: 'ok',
};

export const SEVERITY_TONE: Record<string, StatusTone> = {
  bloqueo: 'blocked',
  retencion: 'attention',
  aviso: 'neutral',
};

export const ACCOUNT_TONE: Record<string, StatusTone> = {
  heredada: 'muted',
  registrada: 'attention',
  verificada: 'ok',
  atestada: 'ok',
  rechazada: 'blocked',
};

export const VAT_TONE: Record<string, StatusTone> = {
  abierto: 'neutral',
  listo_revision: 'attention',
  presentado: 'ok',
};
