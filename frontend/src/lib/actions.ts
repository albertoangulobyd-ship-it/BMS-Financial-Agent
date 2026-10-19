// Las ordenes que la app ofrece y el permiso que pide cada una (servicios.ACCIONES; un
// test de Python, tests/test_app_local.py, comprueba que esta tabla dice lo mismo). Un
// boton solo sale si la persona tiene el permiso; aun asi, quien decide es el servidor.
//
// No hay, ni habra, una orden que cree facturas, pague, apruebe un pago o presente el
// btw: no existen en servicios.py y la app no las inventa. btw_anotar_presentacion solo
// anota que una persona ya presento la aangifte en el portal (con su referencia).

export const ACTION_PERMISSION = {
  anular_hallazgo: 'anular_aviso',
  firmar_anulacion: 'anular_aviso',
  cerrar_hallazgo: 'resolver_aviso',
  marcar_revisada: 'revisar_factura',
  devolver_factura: 'revisar_factura',
  anadir_nota: 'anadir_informacion',
  crear_excepcion: 'resolver_aviso',
  asignar_excepcion: 'resolver_aviso',
  esperar_externo: 'resolver_aviso',
  resolver_excepcion: 'resolver_aviso',
  confirmar_relacion: 'anular_acreditar',
  rechazar_relacion: 'anular_acreditar',
  verificar_iban: 'confirmar_iban',
  rechazar_iban: 'confirmar_iban',
  atestar_iban: 'confirmar_iban',
  // El estado de un trimestre del btw (pantalla Btw). Ninguna presenta nada: la aangifte la
  // hace una persona en el portal de la Belastingdienst y aqui solo se anota que se hizo.
  btw_lista_para_revision: 'gestionar_btw',
  btw_reabrir: 'gestionar_btw',
  btw_anotar_presentacion: 'gestionar_btw',
} as const;

export type ActionName = keyof typeof ACTION_PERMISSION | 'fijar_campo' | 'verificar_campo' | 'revertir_campo';

/** El permiso de una orden; las de campos dependen del campo (lo decide el servidor). */
export function permissionFor(action: ActionName, fieldHasValue = true): string {
  if (action === 'fijar_campo') return fieldHasValue ? 'editar_extraccion' : 'anadir_informacion';
  if (action === 'verificar_campo' || action === 'revertir_campo') return 'editar_extraccion';
  return ACTION_PERMISSION[action];
}

/** Anular (aceptar) un hallazgo pide un motivo de al menos tantos caracteres. */
export const MIN_ACCEPT_REASON = 10;
