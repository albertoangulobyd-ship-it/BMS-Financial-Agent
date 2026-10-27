// El glosario del castellano (revision del paso 16): es.ts y es.json salen en la misma pantalla
// y decian IVA y BTW, abono y nota de credito, aviso y hallazgo, fichero y archivo, relacion y
// parte, apuntar y anotar. La clave es la palabra que se usa; la expresion, lo que ya no puede
// salir. Lo usan i18n.test.ts (es.ts y es.json) y e2e/fixtures.ts (lo que se ve en cada pantalla
// en castellano); tests/test_textos_es.py comprueba lo mismo en Python. La app no lo importa.
// BTW solo vale como nombre neerlandes entre parentesis ("Número de IVA (BTW)") y en "BTW
// verlegd" (el regimen, tal como lo imprime la factura). Aviso es la gravedad de un hallazgo.
/** Una expresion con limites de palabra de verdad: el \b de JavaScript no sabe de tildes (en
 *  "tenía el" veia "a el"). */
function words(pattern: string, flags = ''): RegExp {
  return new RegExp(`(?<!\\p{L})(?:${pattern})(?!\\p{L})`, `u${flags}`);
}

export const ES_GLOSSARY: Readonly<Record<string, RegExp>> = {
  IVA: words('BTW(?! verlegd| en neerlandés\\))(?<!\\(BTW)'),
  'nota de crédito': words('abonos?', 'i'),
  hallazgo: words('avisos? (?:que bloquea|tal como|para esta factura|nuevos)|aceptar (?:el|este) aviso', 'i'),
  archivo: words('ficheros?', 'i'),
  empresa: words('relación|relacion|(?:la|una|otra|esta|misma) parte', 'i'),
  anotar: words('apunt(?:ar|ad[oa]s?|a|o|ó)', 'i'),
  'al (a + el)': words('a el'),
};

/** Las palabras del glosario que un texto en castellano no deberia usar ("archivo <- fichero"). */
export function glossaryMisses(text: string): string[] {
  return Object.entries(ES_GLOSSARY)
    .filter(([, rejected]) => rejected.test(text))
    .map(([word, rejected]) => `${word} <- ${rejected.exec(text)![0]}`);
}
