// El logotipo de BMS como un SVG pequeno (paso 16). Aurora llevaba el logotipo como un PNG de
// 114 KB dentro del codigo y lo pintaba en blanco con un filtro; aqui es su silueta ("BMS //"),
// trazada una vez desde ese PNG (marching squares y Douglas-Peucker sobre la luminancia), con
// currentColor: sirve en los dos temas y no pesa nada. Al lado, "finance" en IBM Plex.
import { cn } from '@/lib/utils';

const BMS_PATH = [
  'M232 16L240 16.4L248 17.9L254 20.6L258 23.1L263 28.1L265.4 32L267.4 37L268.2 42L267 42.7',
  'L243 42.7L242 42L241.5 40L239.4 37L236 35.6L231 34.7L230 35.3L227 35.6L225 36.7L223.9 38',
  'L223.3 40L223.6 43L229 46.2L252 52.6L259 55.5L262 57.6L264 59.2L268.3 65L270.3 71L270.5 79',
  'L269.4 85L267.2 90L263.5 95L258 99.3L253 101.7L247 103.5L239 104.7L224 104.4L215 102.4L209 99.5',
  'L205 96.7L200.6 92L197.5 86L195.3 78L196 75.8L198 76.4L221 76.1L223.8 81L226 82.8L230 84.3',
  'L233 84.5L237 84.4L241 83.1L243.6 80L243.7 78L243 76.4L239 73.5L235 71.8L216 66.6L210 64.4',
  'L206 62.2L203.4 60L200 55.8L197.3 49L196.8 41L197.7 35L199.7 30L203.8 25L208 21.6L214 18.7',
  'L222 16.7Z',
  'M326 16L345 16.3L351 15.9L351.7 17L333.6 62L333.2 64L325.7 82L325.5 84L324.4 87L317 104.7',
  'L291 105.1L290.4 104L293.6 96L294.7 95Z',
  'M366.9 16L392 15.8L393 15.9L393.3 17L358 104.9L332 104.9L331.4 104L346.4 68Z',
  'M150.9 18L183 18L183.6 19L183.6 102L183 102.7L160 102.7L158.9 102L159.5 53L159 48.7L145.5 102',
  'L145 102.6L127 102.5L126.1 101L122.5 87L114.8 57L114.5 53L113 48.7L112.3 52L113.1 55L112.7 56',
  'L113.2 61L113.2 102L112 102.5L89 102.3L88.6 101L89 96L88.7 19L90 18.3L120 18.2L122 18.9',
  'L123.5 26L132.5 58L135.1 69L136 70.9L138.8 59Z',
  'M0.3 19L1 18.2L47 18.5L55 19.4L60 21L65 23.7L68 26.4L71.1 31L72.2 35L72.5 44L70 50.6L67.5 54',
  'L63.2 57L63.4 58L67 59.6L70 61.8L73 65.4L75.3 72L75.4 76L75.3 82L74.3 87L71 92.8L67.9 96',
  'L63 99.1L59 100.7L50 102.3L1 102.8L0.2 102Z',
  'M26 37.9L26.2 51L27 52.3L41 51.8L45 50.5L46 49.9L47.1 48L47.6 42L46.7 40L45 38.5L41 37.5Z',
  'M35 66.9L27 67.3L26.5 68L26.4 82L27 82.7L44 82.3L47 81.3L48.6 80L50.4 77L50.5 73L49 70L47 68.3',
  'L45 67.6Z',
].join('');

/** La silueta "BMS //", del color del texto. Decorativa salvo que se le de un nombre. */
export function BmsMark({ className, title }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox='0 14 395 93'
      className={cn('block h-auto', className)}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      focusable='false'
    >
      <path fill='currentColor' fillRule='evenodd' d={BMS_PATH} />
    </svg>
  );
}

/** La marca de Aurora: "BMS //" y, separado por una linea fina, "finance". */
export function BmsLogo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-3 text-foreground', className)} role='img' aria-label='BMS finance'>
      <BmsMark className={compact ? 'w-[64px]' : 'w-[96px]'} />
      {!compact && (
        <span aria-hidden='true' className='border-l border-border pl-3 text-[14px] font-medium tracking-[-0.01em]'>
          finance
        </span>
      )}
    </span>
  );
}
