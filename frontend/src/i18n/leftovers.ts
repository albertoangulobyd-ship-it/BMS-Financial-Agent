// Restos de otro idioma (paso 16). Con tres idiomas, "nada de castellano" ya no vale: cada
// idioma tiene que estar libre de palabras que solo son de los otros dos. Son listas de
// palabras que existen en un idioma y no en los otros (sin las que coinciden: "de", "en",
// "is", "open", "week", "account", "data", "was", "has", "import"...), en minusculas.
// Lo usan i18n.test.ts (los diccionarios de la app) y e2e/fixtures.ts (lo que se ve en cada
// pantalla); la app no lo importa. Una palabra que salte aqui por un nombre propio o por el
// texto de un documento va con data-proper-name en la pantalla, no se quita de la lista.
import type { Lang } from './langs';

const WORDS: Record<Lang, readonly string[]> = {
  nl: [
    'factuur', 'facturen', 'leverancier', 'leveranciers', 'klant', 'klanten', 'openstaand',
    'vervallen', 'vervaldatum', 'geblokkeerd', 'betaald', 'betaling', 'betalen', 'bedrag',
    'bedragen', 'waarom', 'prioriteit', 'controle', 'gecontroleerd', 'uitzondering',
    'uitzonderingen', 'instellingen', 'overzicht', 'werklijst', 'inkomend', 'uitgaand',
    'kasstroom', 'importeren', 'lezen', 'niet', 'nog', 'geen', 'het', 'een', 'wordt',
    'worden', 'zijn', 'deze', 'dit', 'wat', 'welke', 'alle', 'ook', 'naar', 'bij', 'zoek',
    'opnieuw', 'laden', 'sluiten', 'openen', 'annuleren', 'opslaan', 'verbergen', 'tonen',
    'dagen', 'vandaag', 'maand', 'jaar', 'kwartaal', 'aangifte', 'afscherming', 'gegevens',
    'bezwaren', 'systeem', 'wachten', 'iemand', 'eerst', 'proberen', 'bestand',
    'persoonlijke', 'inloggen', 'uitloggen', 'taal', 'thema', 'donker', 'licht', 'volg',
    'eerste', 'nodig', 'aandacht', 'heeft', 'hebben', 'moet', 'kan', 'wij', 'jij', 'je',
  ],
  en: [
    'the', 'and', 'invoice', 'invoices', 'provider', 'providers', 'client', 'clients',
    'outstanding', 'overdue', 'paid', 'blocked', 'not', 'with', 'from', 'this', 'that',
    'these', 'what', 'which', 'your', 'you', 'are', 'were', 'have', 'been',
    'will', 'would', 'should', 'there', 'here', 'still', 'yet', 'already', 'only', 'after',
    'before', 'when', 'where', 'who', 'why', 'how', 'show', 'hide', 'search', 'close',
    'settings', 'overview', 'queue', 'exceptions', 'checks', 'reading', 'money',
    'cash', 'flow', 'purchase', 'sales', 'amount', 'due', 'today', 'month', 'year', 'quarter',
    'filed', 'loading', 'again', 'reload', 'cancel', 'save', 'unknown', 'nothing',
    'something', 'someone', 'everything', 'people', 'theme', 'dark', 'light', 'follow',
    'language', 'logged', 'signed', 'needs', 'attention',
  ],
  // Las de e2e/fixtures.ts del paso 15 (afinadas para no coincidir con el neerlandes ni el
  // ingles), mas unas pocas.
  es: [
    'finanzas', 'factura', 'facturas', 'proveedor', 'proveedores', 'cliente', 'clientes',
    'pendiente', 'pendientes', 'vencida', 'vencidas', 'vencido', 'hallazgo', 'hallazgos',
    'excepción', 'excepcion', 'excepciones', 'importe', 'importes', 'fecha', 'fechas',
    'motivo', 'motivos', 'regla', 'reglas', 'revisión', 'revisada', 'pagada', 'pagado',
    'pagar', 'pago', 'pagos', 'abierta', 'abierto', 'cerrada', 'cerrado', 'aceptado',
    'aceptada', 'objeto', 'objetos', 'ninguno', 'ninguna', 'también', 'según', 'está',
    'están', 'aquí', 'datos', 'trimestre', 'presentado', 'presentar', 'bloqueada', 'cuenta',
    'cuentas', 'bancaria', 'periodo', 'semana', 'hoy', 'lista', 'listo', 'nueva', 'nuevo',
    'añadir', 'guardar', 'cancelar', 'cerrar', 'abrir', 'buscar', 'importar', 'empresa',
    'copia', 'estado', 'resumen', 'iva', 'aprobado', 'aprobar', 'cobro', 'cobrado',
    'órdenes', 'qué', 'para', 'pero', 'una', 'uno', 'del', 'por', 'sí', 'línea', 'líneas',
    'número', 'código', 'después', 'antes', 'cuando', 'porque', 'todavía', 'aún',
  ],
};

const SETS: Record<Lang, ReadonlySet<string>> = {
  nl: new Set(WORDS.nl),
  en: new Set(WORDS.en),
  es: new Set(WORDS.es),
};

/** Las palabras de un texto que son solo de `other` (sin repetir), en minusculas. */
export function wordsOf(text: string, other: Lang): string[] {
  // Los huecos de una plantilla ({what}) no son texto.
  const plain = text.replace(/\{[a-zA-Z0-9_]+\}/g, ' ');
  const found = (plain.toLocaleLowerCase('nl-NL').match(/\p{L}+/gu) ?? []).filter((w) => SETS[other].has(w));
  return [...new Set(found)];
}

/** Las palabras de los idiomas que no son `lang` que aparecen en un texto en `lang`. */
export function leftoversIn(text: string, lang: Lang, ignore: readonly Lang[] = []): string[] {
  const others = (Object.keys(SETS) as Lang[]).filter((l) => l !== lang && !ignore.includes(l));
  return others.flatMap((other) => wordsOf(text, other).map((w) => `${other}:${w}`));
}

/** Para comprobar las listas: ninguna palabra puede estar en dos idiomas a la vez. */
export function sharedWords(): string[] {
  const all = Object.entries(WORDS).flatMap(([lang, words]) => words.map((w) => [lang, w] as const));
  return all.filter(([lang, w]) => all.some(([l, x]) => l !== lang && x === w)).map(([l, w]) => `${l}:${w}`);
}
