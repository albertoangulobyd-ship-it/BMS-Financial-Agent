// Los dos textos que la vista previa anade a la app, en sus tres idiomas. Van a dos sitios:
// - al catalogo de errores de la app (textos/<idioma>.json, seccion "errores"), con las claves
//   de los dos codigos que contesta el shim (vista_previa y vista_previa_descarga): asi la app
//   los dice donde dice cualquier error de una orden o de una descarga (construir.mjs);
// - al aviso de la pagina (#vp-aviso), que pone el shim cuando una orden no se guarda.
export const TEXTOS_VP = {
  nl: {
    vista_previa:
      'Dit is een voorbeeldweergave met testgegevens: acties worden hier niet uitgevoerd of opgeslagen. In de echte app wordt deze actie wel uitgevoerd.',
    vista_previa_descarga:
      'Dit is een voorbeeldweergave met testgegevens: downloaden kan hier niet. In de echte app kun je dit bestand wel downloaden.',
  },
  en: {
    vista_previa:
      'This is a preview with test data: actions are not carried out or saved here. In the real app this action is carried out.',
    vista_previa_descarga:
      'This is a preview with test data: downloads are not available here. In the real app you can download this file.',
  },
  es: {
    vista_previa:
      'Esto es una vista previa con datos de prueba: aquí las acciones no se hacen ni se guardan. En la app de verdad esta acción sí se hace.',
    vista_previa_descarga:
      'Esto es una vista previa con datos de prueba: aquí no se puede descargar. En la app de verdad sí puedes descargar este archivo.',
  },
};
