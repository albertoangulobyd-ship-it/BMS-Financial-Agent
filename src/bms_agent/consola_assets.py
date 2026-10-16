"""La consola interna: su pagina, su script y su estilo, como texto.

La pagina no lleva ningun dato: todo llega despues por /api/v2 en JSON y el
script lo pinta con createElement y textContent. Nada de lo que viene de un
documento (un nombre, una descripcion, las notas del PDF) se interpreta
nunca como HTML: no hay innerHTML, ni insertAdjacentHTML, ni document.write,
ni atributos de evento escritos como texto. Y aunque lo hubiera, la politica
de contenido del servidor (consola.py) solo deja ejecutar el script propio,
no uno que venga dentro de los datos.

El token de la persona se escribe al entrar y vive solo en la memoria de la
pagina: no se guarda en el navegador ni viaja en la URL.
"""

from __future__ import annotations

PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>bms-agent, consola</title>
<link rel="stylesheet" href="/consola.css">
<script src="/consola.js" defer></script>
</head>
<body>
<header>
  <h1>Consola interna</h1>
  <p class="aviso">Revisar no aprueba ningún pago. «Sin objeciones del sistema» quiere decir
  que las reglas no ven nada, no que una persona lo haya mirado.</p>
  <form id="entrar">
    <label>Token personal <input id="token" type="password" autocomplete="off" required></label>
    <button type="submit">Entrar</button>
    <span id="quien"></span>
  </form>
</header>
<main>
  <section id="fuentes"></section>
  <section id="mensaje" role="status"></section>
  <section id="lista"></section>
  <section id="partes"></section>
  <section id="ordenes"></section>
  <section id="ficha"></section>
</main>
</body>
</html>
"""

ESTILO = """
:root{--fondo:#ffffff;--texto:#141a23;--suave:#5b6573;--linea:#d9dee5;--bloq:#a4161a;
--urg:#d9480f;--aten:#b08900;--ok:#2b8a3e;--caja:#f3f5f8}
body{font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:78rem;padding:0 1rem;
color:var(--texto);background:var(--fondo)}
header{border-bottom:1px solid var(--linea);padding:.5rem 0}
h1{font-size:1.3rem;margin:.3rem 0}
h2{font-size:1.1rem;margin:1.2rem 0 .4rem}
h3{font-size:1rem;margin:.9rem 0 .3rem}
.aviso{color:var(--suave);margin:.2rem 0 .6rem}
.pasada{color:var(--bloq);font-weight:600}
table{border-collapse:collapse;width:100%;margin:.3rem 0}
th,td{border-bottom:1px solid var(--linea);padding:.25rem .4rem;text-align:left;vertical-align:top}
th{font-weight:600;background:var(--caja)}
tr.fila{cursor:pointer}
tr.fila:hover{background:var(--caja)}
.insignia{display:inline-block;border-radius:.3rem;padding:0 .35rem;font-size:.8rem;
font-weight:600;border:1px solid currentColor}
.bloqueada{color:var(--bloq)}.urgente{color:var(--urg)}.atencion{color:var(--aten)}
.normal{color:var(--suave)}.verificado{color:var(--ok)}
.faltante,.discrepancia{color:var(--bloq)}.anomalia{color:var(--urg)}.dudoso{color:var(--aten)}
.doc{background:#fff8e6;border:1px dashed var(--aten);padding:.5rem;white-space:pre-wrap}
.caja{background:var(--caja);padding:.5rem;margin:.4rem 0}
form.linea{display:flex;flex-wrap:wrap;gap:.3rem;align-items:center;margin:.2rem 0}
input,select,button,textarea{font:inherit}
#mensaje{white-space:pre-wrap;margin:.5rem 0}
.error{color:var(--bloq)}
.suave{color:var(--suave)}
"""

SCRIPT = r"""
(function () {
  'use strict';

  var estado = {token: null, yo: null, acciones: {}, personas: [], objetos: [], ordenes: [],
                ficha: null};

  // ---------------------------------------------------------------- DOM

  // Un elemento con sus atributos y sus hijos. Un hijo que no es un nodo se
  // pone siempre como texto: es la unica forma en que un dato entra en la
  // pagina.
  function el(etiqueta, atributos) {
    var nodo = document.createElement(etiqueta);
    var claves = Object.keys(atributos || {});
    for (var i = 0; i < claves.length; i++) {
      var clave = claves[i];
      var valor = atributos[clave];
      if (valor === null || valor === undefined || valor === false) { continue; }
      if (clave === 'clase') { nodo.className = String(valor); }
      else if (clave === 'al_pulsar') { nodo.addEventListener('click', valor); }
      else if (clave === 'al_enviar') { nodo.addEventListener('submit', valor); }
      else if (clave === 'valor') { nodo.value = String(valor); }
      else if (/^on/i.test(clave)) { throw new Error('atributo de evento no admitido: ' + clave); }
      else { nodo.setAttribute(clave, String(valor)); }
    }
    for (var j = 2; j < arguments.length; j++) { poner(nodo, arguments[j]); }
    return nodo;
  }

  // Todos los argumentos tras el nodo son hijos, como en el().
  function anadir(nodo) {
    for (var i = 1; i < arguments.length; i++) { poner(nodo, arguments[i]); }
  }

  function poner(nodo, hijo) {
    if (hijo === null || hijo === undefined || hijo === false) { return; }
    if (Array.isArray(hijo)) { for (var i = 0; i < hijo.length; i++) { poner(nodo, hijo[i]); } return; }
    if (typeof hijo === 'object' && hijo.nodeType) { nodo.appendChild(hijo); return; }
    nodo.appendChild(document.createTextNode(String(hijo)));
  }

  function vaciar(nodo) { while (nodo.firstChild) { nodo.removeChild(nodo.firstChild); } }

  function insignia(texto, clase) {
    return el('span', {clase: 'insignia ' + (clase || '')}, texto);
  }

  var ETIQUETA_NIVEL = {bloqueada: 'Bloqueada', urgente: 'Urgente', atencion: 'Atención',
                        normal: 'Normal'};
  var ETIQUETA_REVISION = {sin_revisar: 'Sin revisar', necesita_revision: 'Necesita revisión',
                           revisada: 'Revisada'};

  function nuevoId() {
    if (window.crypto && window.crypto.randomUUID) { return window.crypto.randomUUID(); }
    return 'p-' + Date.now() + '-' + Math.random().toString(16).slice(2);
  }

  // ---------------------------------------------------------------- API

  function api(metodo, ruta, cuerpo) {
    var cabeceras = {'X-BMS-Token': estado.token || ''};
    var opciones = {method: metodo, headers: cabeceras};
    if (cuerpo !== undefined) {
      cabeceras['Content-Type'] = 'application/json';
      opciones.body = JSON.stringify(cuerpo);
    }
    return fetch(ruta, opciones).then(function (r) {
      return r.json().then(function (datos) {
        if (!r.ok) { throw new Error(datos.error || ('error ' + r.status)); }
        return datos;
      });
    });
  }

  function decir(texto, esError) {
    var caja = document.getElementById('mensaje');
    vaciar(caja);
    anadir(caja, el('p', {clase: esError ? 'error' : ''}, texto));
  }

  function resumen(diferencia) {
    if (diferencia.repetida) { return 'Esa petición ya se había aplicado: no se repite.'; }
    if (diferencia.evento_id === null) { return 'No cambia nada.'; }
    var partes = ['Hecho (evento ' + diferencia.evento_id + ').'];
    var grupos = diferencia.hallazgos || {};
    Object.keys(grupos).forEach(function (clave) {
      partes.push('Hallazgos ' + clave + ': ' + grupos[clave].map(function (h) {
        return h.regla; }).join(', '));
    });
    (diferencia.prioridades || []).forEach(function (p) {
      partes.push('Prioridad de ' + p.entidad + ' ' + p.entidad_id + ': ' +
                  (p.antes || '-') + ' → ' + (p.despues || '-'));
    });
    (diferencia.revisiones_invalidadas || []).forEach(function (f) {
      partes.push('La revisión de la factura ' + f + ' deja de valer.');
    });
    (diferencia.totales || []).forEach(function (t) {
      partes.push(t.entidad + ' ' + t.id + ' ' + t.campo + ': ' + t.antes + ' → ' + t.despues);
    });
    return partes.join('\n');
  }

  // Una orden: su peticion_id se fija al pintar el formulario, asi que
  // pulsar dos veces no la aplica dos veces.
  function ordenar(nombre, datos, peticion) {
    var cuerpo = {accion: nombre, peticion_id: peticion, datos: datos};
    return api('POST', '/api/v2/acciones', cuerpo).then(function (r) {
      decir(resumen(r.diferencia), false);
      return recargar();
    }).catch(function (error) { decir('No se hace: ' + error.message, true); });
  }

  function formulario(nombre, campos, datosFijos, textoBoton, opciones) {
    var peticion = nuevoId();
    var entradas = {};
    var enLista = {};
    campos.forEach(function (c) { enLista[c.nombre] = !!c.lista; });
    var hijos = campos.map(function (c) {
      var entrada;
      if (c.opciones) {
        entrada = el('select', {name: c.nombre});
        c.opciones.forEach(function (o) {
          anadir(entrada, el('option', {valor: o[0]}, o[1]));
        });
      } else {
        entrada = el('input', {name: c.nombre, type: c.tipo || 'text', placeholder: c.ayuda || '',
                               valor: c.valor === undefined || c.valor === null ? '' : c.valor});
      }
      entradas[c.nombre] = entrada;
      return el('label', {}, (c.etiqueta || c.nombre) + ' ', entrada);
    });
    var form = el('form', {clase: 'linea', al_enviar: function (ev) {
      ev.preventDefault();
      var datos = {};
      Object.keys(datosFijos).forEach(function (k) { datos[k] = datosFijos[k]; });
      Object.keys(entradas).forEach(function (k) {
        var v = entradas[k].value;
        if (v !== '') { datos[k] = enLista[k] ? [parseInt(v, 10)] : v; }
      });
      ordenar(nombre, datos, peticion);
    }}, hijos, el('button', {type: 'submit'}, textoBoton));
    if (opciones && opciones.titulo) { return el('div', {}, el('span', {clase: 'suave'}, opciones.titulo), form); }
    return form;
  }

  // ---------------------------------------------------------------- lista

  function pintarListado(contenedor, facturas) {
    vaciar(contenedor);
    var cabecera = el('tr', {}, ['Prioridad', 'Puntos', 'Factura', 'Contraparte', 'Total',
      'Vence', 'Revisión', 'Calidad', 'Ediciones', 'Sistema'].map(function (t) {
        return el('th', {}, t); }));
    var cuerpo = el('tbody');
    facturas.forEach(function (f) {
      var ediciones = [];
      if (f.corregida) { ediciones.push('corregida'); }
      if (f.suplementada) { ediciones.push('suplementada'); }
      if (f.sin_resolver) { ediciones.push(f.sin_resolver + ' sin resolver'); }
      var fila = el('tr', {clase: 'fila', al_pulsar: function () { abrirFicha(f.id); }},
        el('td', {}, insignia(ETIQUETA_NIVEL[f.nivel] || f.nivel, f.nivel)),
        el('td', {}, String(f.puntos)),
        el('td', {}, f.numero || '(sin número)'),
        el('td', {}, f.contraparte || ''),
        el('td', {}, f.total || ''),
        el('td', {}, f.vencimiento || ''),
        el('td', {}, ETIQUETA_REVISION[f.estado_revision] || ''),
        el('td', {}, f.calidad ? insignia(f.calidad, f.calidad) : ''),
        el('td', {}, ediciones.join(', ')),
        el('td', {}, f.etiqueta, f.motivos && f.motivos.length ?
          el('div', {clase: 'suave'}, f.motivos.join(' · ')) : null));
      anadir(cuerpo, fila);
    });
    anadir(contenedor, el('h2', {}, 'Facturas'), el('table', {}, el('thead', {}, cabecera), cuerpo));
  }

  // ---------------------------------------------------------------- ficha

  function tablaCampos(campos, conAcciones) {
    var cuerpo = el('tbody');
    campos.forEach(function (c) {
      if (c.valor === null && c.original_crudo === null && !c.obligatorio) { return; }
      var marcas = [];
      if (c.suplementado) { marcas.push('suplido a mano'); }
      if (c.corregido) { marcas.push('corregido a mano'); }
      if (c.sin_resolver) { marcas.push('sin resolver'); }
      if (c.dudoso) { marcas.push('dudoso'); }
      if (c.verificado) { marcas.push('verificado'); }
      var original = c.editado ? [c.original_texto === null ? '(vacío)' : c.original_texto,
        c.original_crudo !== null ? ' (impreso: ' + c.original_crudo + ')' : ''] :
        (c.original_crudo !== null && c.original_crudo !== c.texto ? 'impreso: ' + c.original_crudo : '');
      var acciones = [];
      if (conAcciones && c.editable) {
        acciones.push(formulario('fijar_campo', [
          {nombre: 'valor', etiqueta: c.valor === null ? 'Rellenar' : 'Corregir', valor: c.entrada},
          {nombre: 'motivo', etiqueta: 'motivo'}],
          {tabla: c.tabla, fila_id: c.fila_id, campo: c.campo, rev: c.rev}, 'Guardar'));
        if (c.valor !== null && !c.verificado) {
          acciones.push(formulario('verificar_campo', [],
            {tabla: c.tabla, fila_id: c.fila_id, campo: c.campo, rev: c.rev}, 'Verificar'));
        }
        if (c.revertible) {
          acciones.push(formulario('revertir_campo', [{nombre: 'motivo', etiqueta: 'motivo'}],
            {tabla: c.tabla, fila_id: c.fila_id, campo: c.campo, rev: c.rev}, 'Deshacer'));
        }
      }
      anadir(cuerpo, el('tr', {},
        el('td', {}, c.campo),
        el('td', {}, c.texto === null ? '' : c.texto),
        el('td', {}, original),
        el('td', {}, c.fuente || ''),
        el('td', {}, c.calidad ? insignia(c.calidad, c.calidad) : ''),
        el('td', {}, marcas.join(', '), c.cambiado_por && c.editado ?
          el('div', {clase: 'suave'}, (c.cambiado_por) + ', ' + (c.cambiado_en || '')) : null),
        el('td', {}, acciones)));
    });
    var cabecera = el('tr', {}, ['Campo', 'Valor actual', 'Original', 'Fuente', 'Calidad',
      'Marcas', ''].map(function (t) { return el('th', {}, t); }));
    return el('table', {}, el('thead', {}, cabecera), cuerpo);
  }

  function conRev(campos, rev) {
    return campos.map(function (c) { var copia = {}; Object.keys(c).forEach(function (k) {
      copia[k] = c[k]; }); copia.rev = rev; return copia; });
  }

  function pintarHallazgos(f) {
    var lista = el('div');
    if (!f.hallazgos.length) { anadir(lista, el('p', {clase: 'suave'}, 'Ningún hallazgo pendiente.')); }
    f.hallazgos.forEach(function (h) {
      var acciones = [];
      if (h.anulable && (h.estado === 'abierto' || h.estado === 'aceptado')) {
        acciones.push(formulario('anular_hallazgo', [
          {nombre: 'motivo', etiqueta: 'motivo (10+)'},
          {nombre: 'vigente_hasta', etiqueta: 'hasta', tipo: 'date'}],
          {hallazgo_id: h.id, huella: h.huella}, 'Anular'));
        // La segunda firma la da la otra persona desde su propia sesion, para quien
        // va a anular: nadie escribe aqui el token de otro.
        if (h.segunda_firma) {
          acciones.push(formulario('firmar_anulacion', [
            {nombre: 'solicitante_id', etiqueta: 'la anula', opciones:
              estado.personas.map(function (p) { return [String(p.id), p.nombre]; })},
            {nombre: 'vigente_hasta', etiqueta: 'hasta', tipo: 'date'},
            {nombre: 'motivo', etiqueta: 'motivo'}],
            {hallazgo_id: h.id, huella: h.huella}, 'Dar la segunda firma'));
        }
      }
      if (h.estado === 'desaparecido') {
        acciones.push(formulario('cerrar_hallazgo', [{nombre: 'motivo', etiqueta: 'motivo'}],
          {hallazgo_id: h.id, huella: h.huella}, 'Cerrar'));
      }
      anadir(lista, el('div', {clase: 'caja'},
        insignia(h.severidad, h.severidad === 'bloqueo' ? 'bloqueada' :
          (h.severidad === 'retencion' ? 'atencion' : 'normal')), ' ',
        el('strong', {}, h.regla + ' ' + h.titulo), ' ', el('span', {clase: 'suave'}, h.estado),
        el('div', {}, h.detalle), acciones));
    });
    return lista;
  }

  function pintarExcepcion(f) {
    var caja = el('div', {clase: 'caja'});
    var e = f.excepcion;
    if (!e) {
      anadir(caja, el('p', {clase: 'suave'}, 'Sin excepción abierta.'),
        formulario('crear_excepcion', [{nombre: 'titulo', etiqueta: 'asunto'},
          {nombre: 'motivo', etiqueta: 'descripción'}], {tabla: 'factura', fila_id: f.id},
          'Abrir una excepción'));
      return caja;
    }
    anadir(caja, el('p', {}, el('strong', {}, e.titulo), ' — ', e.estado,
      e.responsable ? ', a cargo de ' + e.responsable : '',
      e.esperando_a ? ', esperando a ' + e.esperando_a + ' hasta el ' + e.fecha_seguimiento : ''),
      el('p', {clase: 'suave'}, e.descripcion || ''));
    var personas = estado.personas.map(function (p) { return [String(p.id), p.nombre]; });
    anadir(caja,
      formulario('asignar_excepcion', [{nombre: 'responsable_id', etiqueta: 'a cargo de',
        opciones: personas}], {excepcion_id: e.id, rev: e.rev}, 'Asignar'),
      formulario('esperar_externo', [{nombre: 'esperando_a', etiqueta: 'esperando a', opciones: [
        ['proveedor', 'proveedor'], ['cliente', 'cliente'], ['contable', 'contable'],
        ['exact', 'Exact'], ['trnsprnt', 'TRNSPRNT'], ['banco', 'banco'], ['otro', 'otro']]},
        {nombre: 'fecha_seguimiento', etiqueta: 'seguimiento', tipo: 'date'},
        {nombre: 'motivo', etiqueta: 'nota'}], {excepcion_id: e.id, rev: e.rev}, 'Esperar'),
      formulario('resolver_excepcion', [{nombre: 'resolucion', etiqueta: 'resolución', opciones: [
        ['corregido', 'corregido'], ['aceptado', 'aceptado'], ['anulado', 'anulado'],
        ['no_procede', 'no procede'], ['condicion_desaparecida', 'condición desaparecida']]},
        {nombre: 'motivo', etiqueta: 'notas'}], {excepcion_id: e.id, rev: e.rev}, 'Resolver'));
    return caja;
  }

  function pintarLineas(f) {
    var caja = el('div');
    f.lineas.forEach(function (l) {
      var objetos = [['', '(sin Objeto)']].concat(estado.objetos.map(function (o) {
        return [String(o.id), o.codigo]; }));
      anadir(caja, el('h3', {}, 'Línea ' + l.orden + (l.retirada ? ' (excluida)' : '')),
        tablaCampos(conRev(l.campos, l.rev), !l.retirada));
      var ordenes = [['', '(sin PO)']].concat(estado.ordenes.map(function (o) {
        return [String(o.id), o.numero + ' (' + (o.parte.nombre || o.lado) + ')']; }));
      l.imputaciones.forEach(function (imp) {
        if (imp.retirada) { return; }
        anadir(caja, el('div', {clase: 'caja'}, 'Imputación ' + imp.id + ': ',
          imp.objeto || '(sin Objeto)', ' · PO ', imp.orden_compra || '(ninguna)',
          formulario('cambiar_objeto', [{nombre: 'objeto_id', etiqueta: 'Objeto', opciones: objetos},
            {nombre: 'motivo', etiqueta: 'motivo'}], {imputacion_id: imp.id, rev: imp.rev},
            'Cambiar imputación'),
          formulario('imputar_po', [{nombre: 'orden_compra_id', etiqueta: 'PO', opciones: ordenes},
            {nombre: 'motivo', etiqueta: 'motivo'}], {imputacion_id: imp.id, rev: imp.rev},
            'Imputar a la PO')));
      });
      if (!l.retirada) {
        anadir(caja, formulario('excluir_linea', [{nombre: 'motivo', etiqueta: 'motivo'}],
          {linea_id: l.id, rev: l.rev}, 'Excluir la línea'));
      }
    });
    return caja;
  }

  // Paso 8: con que otras facturas esta relacionada. Lo propuesto (por el
  // documento o por Exact) no mueve nada hasta que una persona lo confirma.
  var TIPOS_RELACION = [['acredita', 'acredita (abono)'], ['anula', 'anula (abono)'],
    ['sustituye', 'sustituye'], ['corrige', 'corrige'], ['relacionada', 'relacionada']];

  function pintarRelaciones(f) {
    var caja = el('div');
    (f.relaciones || []).forEach(function (r) {
      var acciones = [];
      if (!r.retirada && r.estado === 'propuesta') {
        acciones.push(formulario('confirmar_relacion', [
          {nombre: 'tipo', etiqueta: 'como', opciones: TIPOS_RELACION.filter(function (t) {
            return t[0] === r.tipo; }).concat(TIPOS_RELACION.filter(function (t) {
            return t[0] !== r.tipo; }))},
          {nombre: 'importe', etiqueta: 'importe (si es parcial)'},
          {nombre: 'motivo', etiqueta: 'motivo'}], {relacion_id: r.id, rev: r.rev}, 'Confirmar'));
        acciones.push(formulario('rechazar_relacion', [{nombre: 'motivo', etiqueta: 'motivo'}],
          {relacion_id: r.id, rev: r.rev}, 'Rechazar'));
      } else if (!r.retirada && r.estado === 'confirmada') {
        acciones.push(formulario('retirar_relacion', [{nombre: 'motivo', etiqueta: 'motivo'}],
          {relacion_id: r.id, rev: r.rev}, 'Retirar'));
      }
      anadir(caja, el('div', {clase: 'caja'},
        el('strong', {}, (r.origen_numero || r.origen_id) + ' ' + r.tipo + ' ' +
          (r.destino_numero || r.destino_id)), ' ',
        el('span', {clase: 'suave'}, r.estado + (r.retirada ? ' (retirada)' : '') + ', de ' +
          r.fuente), r.evidencia_doc ? el('div', {clase: 'doc'}, r.evidencia_doc) : null,
        acciones));
    });
    (f.citas || []).forEach(function (c) {
      if (c.retirada) { return; }
      anadir(caja, el('p', {clase: 'suave'}, 'El documento nombra la factura ' +
        (c.numero || '?') + ' (' + c.relacion + ')'));
    });
    anadir(caja, formulario('enlazar_facturas', [
      {nombre: 'destino_id', etiqueta: 'con la factura (id)'},
      {nombre: 'tipo', etiqueta: 'esta factura la', opciones: TIPOS_RELACION},
      {nombre: 'importe', etiqueta: 'importe (abono parcial)'},
      {nombre: 'motivo', etiqueta: 'motivo'}], {origen_id: f.id}, 'Enlazar'));
    return caja;
  }

  function pintarDetalle(contenedor, f) {
    vaciar(contenedor);
    var e = f.estado || {};
    anadir(contenedor,
      el('h2', {}, 'Factura ' + (f.numero || '(sin número)') + ' — ' + (f.contraparte || '')),
      el('p', {}, insignia(ETIQUETA_NIVEL[e.nivel] || e.nivel || '', e.nivel), ' ',
        String(e.puntos || 0) + ' puntos · ', ETIQUETA_REVISION[e.estado_revision] || '', ' · ',
        el('strong', {}, f.etiqueta)),
      el('ul', {}, (e.motivos || []).map(function (m) { return el('li', {}, m); })),
      f.pide_revision.length ? el('div', {clase: 'caja'}, 'Antes de revisarla: ',
        el('ul', {}, f.pide_revision.map(function (m) { return el('li', {}, m); }))) : null,
      el('h3', {}, 'Revisión'),
      formulario('marcar_revisada', [{nombre: 'motivo', etiqueta: 'nota'}],
        {factura_id: f.id, huella: f.huella_contenido}, 'Marcar revisada'),
      formulario('devolver_factura', [{nombre: 'motivo', etiqueta: 'por qué'}],
        {factura_id: f.id, huella: f.huella_contenido}, 'Devolver'),
      el('ul', {}, f.revisiones.map(function (r) {
        return el('li', {}, r.resultado + ' por ' + r.usuario + ' el ' + r.en +
          (r.autorrevisada ? ' (autorrevisada)' : '') + (r.vigente ? '' : ' — ya no vale') +
          (r.nota ? ': ' + r.nota : ''));
      })),
      el('h3', {}, 'Excepción'), pintarExcepcion(f),
      el('h3', {}, 'Hallazgos'), pintarHallazgos(f),
      el('h3', {}, 'Relaciones'), pintarRelaciones(f),
      el('h3', {}, 'Prioridad'),
      formulario('subir_prioridad', [{nombre: 'nivel', etiqueta: 'subir a', opciones: [
        ['atencion', 'Atención'], ['urgente', 'Urgente']]},
        {nombre: 'hasta', etiqueta: 'hasta', tipo: 'date'},
        {nombre: 'motivo', etiqueta: 'motivo (10+)'}], {entidad: 'factura', entidad_id: f.id},
        'Subir'),
      el('h3', {}, 'Campos'), tablaCampos(conRev(f.campos, f.rev), true),
      el('h3', {}, 'Líneas'), pintarLineas(f),
      el('h3', {}, 'Notas internas'),
      el('ul', {}, f.notas.map(function (n) {
        return el('li', {}, n.usuario + ', ' + n.en + ': ', n.texto); })),
      formulario('anadir_nota', [{nombre: 'texto', etiqueta: 'nota'}],
        {tabla: 'factura', fila_id: f.id}, 'Añadir nota'),
      f.notas_doc ? el('div', {}, el('h3', {}, 'Texto del documento (no verificado)'),
        el('div', {clase: 'doc'}, f.notas_doc)) : null,
      el('h3', {}, 'Historia'),
      el('ul', {}, f.historia.map(function (h) {
        return el('li', {}, h.en + ' ' + h.tipo + (h.usuario ? ' (' + h.usuario + ')' : '') +
          (h.motivo ? ': ' + h.motivo : ''));
      })));
  }

  // ---------------------------------------------------------------- proveedores y clientes

  function tablaPartes(titulo, tabla, filas) {
    var cuerpo = el('tbody');
    filas.forEach(function (p) {
      anadir(cuerpo, el('tr', {clase: 'fila', al_pulsar: function () { abrirParte(tabla, p.id); }},
        el('td', {}, p.nombre + (p.activo ? '' : ' (inactivo)')),
        el('td', {}, String(p.facturas)), el('td', {}, p.pendiente || ''),
        el('td', {}, p.vencido || '')));
    });
    var cabecera = el('tr', {}, ['Nombre', 'Facturas', 'Pendiente', 'Vencido'].map(function (t) {
      return el('th', {}, t); }));
    return el('div', {}, el('h2', {}, titulo),
      el('table', {}, el('thead', {}, cabecera), cuerpo));
  }

  function pintarPartes(contenedor, proveedores, clientes) {
    vaciar(contenedor);
    anadir(contenedor, tablaPartes('Proveedores', 'proveedores', proveedores),
      tablaPartes('Clientes', 'clientes', clientes));
  }

  function filas(cabeceras, datos) {
    return el('table', {}, el('thead', {}, el('tr', {}, cabeceras.map(function (t) {
      return el('th', {}, t); }))), el('tbody', {}, datos.map(function (d) {
      return el('tr', {}, d.map(function (v) {
        return el('td', {}, v === null || v === undefined ? '' : String(v)); })); })));
  }

  function pintarParte(contenedor, tabla, v) {
    vaciar(contenedor);
    var pagado = tabla === 'proveedores' ? 'pagado' : 'cobrado';
    var ano = v.ano_facturado, siempre = v.siempre_facturado;
    var plazo = v.plazo_de_pago, tipico = v.importe_tipico;
    anadir(contenedor,
      el('h2', {}, (tabla === 'proveedores' ? 'Proveedor ' : 'Cliente ') + v.nombre),
      el('p', {}, 'Pendiente ' + v.pendiente + ' en ' + v.abiertas + ' facturas · vencido ' +
        v.vencido + ' en ' + v.vencidas + ' (a ' + v.hoy + ')'),
      el('p', {}, v.ano + ': facturado ' + ano.total + ' (' + ano.base + ' sin IVA), ' + pagado +
        ' ' + v.ano_pagado + ' · siempre: ' + siempre.total + ' en ' + siempre.facturas +
        ' facturas, ' + pagado + ' ' + v.siempre_pagado),
      el('p', {clase: 'suave'}, 'Importe típico: ' + (tipico.media || '-') + ' de media, ' +
        (tipico.mediana || '-') + ' de mediana · plazo de pago: ' +
        (plazo.media_dias === null ? '-' : plazo.media_dias + ' días') + ' de media, ' +
        plazo.tarde + ' pagadas tarde'),
      el('h3', {}, 'Por Objeto'),
      filas(['Objeto', 'Facturas', 'Importe', 'Horas'], v.por_objeto.map(function (o) {
        return [o.objeto, o.facturas, o.importe, o.horas]; })),
      v.ibanes ? el('div', {}, el('h3', {}, 'Cuentas'),
        filas(['IBAN', 'Estado', 'Pagable'], v.ibanes.registro.map(function (c) {
          return [c.iban, c.estado, c.pagable ? 'sí' : 'no']; })),
        filas(['IBAN impreso', 'Primera', 'Última', 'Facturas'], v.ibanes.impresos.map(
          function (i) { return [i.iban, i.primera, i.ultima, i.facturas]; }))) : null,
      v.trabajo_sin_facturar ? el('div', {}, el('h3', {}, 'Trabajo sin facturar'),
        v.trabajo_sin_facturar.estado !== 'ok' ?
          el('p', {clase: 'suave'}, v.trabajo_sin_facturar.detalle) :
          filas(['Objeto', 'Desde', 'Hasta', 'Horas', 'Valor'],
            v.trabajo_sin_facturar.periodos.map(function (t) {
              return [t.objeto_id, t.desde, t.hasta, t.horas,
                (t.valor || '-') + (t.estimado ? ' (estimado)' : '')]; }))) : null,
      el('h3', {}, 'Avisos activos'),
      el('ul', {}, v.avisos.hallazgos.map(function (h) {
        return el('li', {}, h.regla + ' (' + h.severidad + ', ' + h.estado + '): ' + h.detalle);
      })),
      el('h3', {}, 'Facturas'),
      el('table', {}, el('tbody', {}, v.historial.map(function (f) {
        return el('tr', {clase: 'fila', al_pulsar: function () { abrirFicha(f.id); }},
          el('td', {}, f.fecha_factura || ''), el('td', {}, f.numero || '(sin número)'),
          el('td', {}, f.total || ''), el('td', {}, f.estado_pago || ''));
      }))),
      el('h3', {}, 'Pagos'),
      filas(['Fecha', 'Factura', 'Importe', 'Fuente'], v.pagos.map(function (p) {
        return [p.fecha, p.numero, p.importe, p.fuente]; })),
      plazo.retrasos.length ? el('div', {}, el('h3', {}, 'Pagos tarde'),
        filas(['Factura', 'Vencía', 'Pagada', 'Días'], plazo.retrasos.map(function (t) {
          return [t.numero, t.vencimiento, t.pagada_el, t.dias]; }))) : null);
  }

  function abrirParte(tabla, id) {
    estado.ficha = null;
    return api('GET', '/api/v2/' + tabla + '/' + encodeURIComponent(String(id))).then(function (r) {
      pintarParte(document.getElementById('ficha'), tabla, r.proveedor || r.cliente);
    }).catch(function (error) { decir(error.message, true); });
  }

  // ---------------------------------------------------------------- ordenes de compra (paso 9)

  function pintarOrdenes(contenedor, ordenes) {
    vaciar(contenedor);
    if (!ordenes.length) { return; }
    var cuerpo = el('tbody');
    ordenes.forEach(function (o) {
      anadir(cuerpo, el('tr', {clase: 'fila', al_pulsar: function () { abrirOrden(o.id); }},
        el('td', {}, insignia(ETIQUETA_NIVEL[o.nivel] || o.nivel, o.nivel)),
        el('td', {}, o.numero + (o.cerrada ? ' (cerrada)' : '')),
        el('td', {}, (o.lado === 'cliente' ? 'de ' : 'a ') + (o.parte.nombre || '?')),
        el('td', {}, o.valor), el('td', {}, o.consumido + ' (' + o.consumido_pct + ')'),
        el('td', {}, o.restante), el('td', {}, o.fecha_fin || ''),
        el('td', {}, o.motivos && o.motivos.length ? o.motivos.join(' · ') : '')));
    });
    var cabecera = el('tr', {}, ['Prioridad', 'PO', 'Parte', 'Valor', 'Consumido', 'Queda',
      'Fin', 'Por qué'].map(function (t) { return el('th', {}, t); }));
    anadir(contenedor, el('h2', {}, 'Órdenes de compra'),
      el('table', {}, el('thead', {}, cabecera), cuerpo));
  }

  function pintarOrden(contenedor, o) {
    vaciar(contenedor);
    var objetos = estado.objetos.map(function (x) { return [String(x.id), x.codigo]; });
    var p = o.prevision;
    anadir(contenedor,
      el('h2', {}, 'PO ' + o.numero + (o.cerrada ? ' (cerrada)' : '')),
      el('p', {}, (o.lado === 'cliente' ? 'Del cliente ' : 'Al proveedor ') +
        (o.parte.nombre || '?') + ' · de ' + (o.fecha_inicio || '…') + ' a ' +
        (o.fecha_fin || '…') + (o.fecha_fin !== o.fecha_fin_original ? ' (fin original ' +
        (o.fecha_fin_original || '…') + ')' : '') + ' · fuente ' + o.fuente),
      el('p', {}, 'Valor ' + o.valor + ' (original ' + o.valor_original + ') · consumido ' +
        o.consumido + ' (' + o.consumido_pct + ') · queda ' + o.restante + ' (' +
        o.restante_pct + '), sin IVA'),
      el('p', {clase: 'suave'}, 'Ritmo: ' + p.consumido_ventana + ' en ' + p.dias +
        ' días desde el ' + p.desde + ' · ' + (p.agotamiento ? 'se agotaría el ' +
        p.agotamiento : 'a este ritmo no se agota')),
      el('p', {clase: 'suave'}, delPlanning('Planificado', o.planificado) + ' · ' +
        delPlanning('Sin facturar', o.sin_facturar)),
      el('h3', {}, 'Objetos'),
      el('ul', {}, o.objetos.length ? o.objetos.map(function (x) {
        return el('li', {clase: 'fila', al_pulsar: function () { abrirObjeto(x.id); }},
          x.codigo + (x.nombre ? ' (' + x.nombre + ')' : ''));
      }) : [el('li', {}, 'Cualquiera de la parte')]),
      el('h3', {}, 'Facturas, en el orden en que la consumen'),
      el('table', {}, el('tbody', {}, o.facturas.map(function (f) {
        return el('tr', {clase: 'fila', al_pulsar: function () { abrirFicha(f.factura_id); }},
          el('td', {}, f.fecha_factura || '(sin fecha)'), el('td', {}, f.numero || ''),
          el('td', {}, f.importe), el('td', {}, 'quedaban ' + f.quedaba));
      }))),
      el('h3', {}, 'Modificaciones'),
      filas(['Desde', 'Valor nuevo', 'Fin nuevo', 'Motivo', 'Quién', 'Cuándo'],
        o.modificaciones.map(function (m) {
          return [m.fecha, m.valor_nuevo, m.fecha_fin_nueva, m.motivo, m.usuario, m.en]; })),
      formulario('modificar_po', [{nombre: 'valor', etiqueta: 'valor nuevo'},
        {nombre: 'fecha_fin', etiqueta: 'fin nuevo', tipo: 'date'},
        {nombre: 'fecha', etiqueta: 'desde', tipo: 'date'},
        {nombre: 'motivo', etiqueta: 'motivo'}], {orden_compra_id: o.id}, 'Apuntar modificación'),
      formulario('cerrar_po', [{nombre: 'cerrada', etiqueta: 'cerrada',
        opciones: o.cerrada ? [['no', 'reabrir'], ['si', 'cerrada']] : [['si', 'cerrar'],
        ['no', 'abierta']]}, {nombre: 'motivo', etiqueta: 'motivo'}],
        {orden_compra_id: o.id, rev: o.rev}, o.cerrada ? 'Reabrir' : 'Cerrar'),
      formulario('objetos_po', [{nombre: 'anadir', etiqueta: 'Objeto', opciones: objetos,
        lista: true},
        {nombre: 'motivo', etiqueta: 'motivo'}], {orden_compra_id: o.id}, 'Añadir Objeto'),
      el('h3', {}, 'Avisos'),
      el('ul', {}, o.avisos.hallazgos.map(function (h) {
        return el('li', {}, h.regla + ' (' + h.severidad + ', ' + h.estado + '): ' + h.detalle);
      })));
  }

  // Lo que sale del planning: su valor, o por que no hay datos (nunca un cero).
  function delPlanning(nombre, bloque) {
    if (bloque.estado !== 'ok') { return bloque.detalle; }
    return nombre + ' ' + bloque.valor + ' (planning)' + (bloque.nota ? ', ' + bloque.nota : '');
  }

  function pintarObjeto(contenedor, v) {
    vaciar(contenedor);
    var h = v.horas;
    var e = h.esperado;
    var semanas = h.semanas.concat([Object.assign({}, h.total, {semana: 'total'})]);
    anadir(contenedor,
      el('h2', {}, 'Objeto ' + v.codigo + (v.nombre ? ' (' + v.nombre + ')' : '')),
      el('p', {}, 'Cliente ' + (v.cliente.nombre || '?') + (v.requiere_po ? ' · pide PO' : '')),
      el('h3', {}, 'Órdenes de compra'),
      filas(['PO', 'Lado', 'Valor', 'Consumido', 'Queda', 'De este Objeto', 'Fin'],
        v.ordenes_compra.map(function (o) {
          return [o.numero + (o.cerrada ? ' (cerrada)' : ''), o.lado, o.valor,
            o.consumido + ' (' + o.consumido_pct + ')', o.restante, o.consumido_objeto,
            o.fecha_fin]; })),
      el('p', {clase: 'suave'}, 'De cliente: queda ' + v.ordenes_resumen.cliente.restante +
        ' de ' + v.ordenes_resumen.cliente.valor + ' · a proveedores: queda ' +
        v.ordenes_resumen.proveedor.restante + ' de ' + v.ordenes_resumen.proveedor.valor),
      el('h3', {}, 'Horas por semana'),
      el('p', {clase: 'suave'}, h.planning === 'ok' ? 'Del planning y de las facturas.' :
        'Sin planning importado: solo las horas facturadas.'),
      filas(['Semana', 'Planificadas', 'Validadas', 'Proveedores', 'Cliente', 'Sin facturar',
        'Dif. proveedor', 'Dif. cliente'], semanas.map(function (f) {
          return [f.semana, f.planificadas || '-', f.validadas || '-', f.proveedor || '-',
            f.cliente || '-', f.sin_facturar || '-', f.diferencia_proveedor || '-',
            f.diferencia_cliente || '-']; })),
      el('p', {}, 'Esperado: por cobrar ' + e.entrante + ' · por pagar ' + e.saliente +
        (e.entrante_estimado !== null ? ' · estimado aparte: por cobrar ' +
          e.entrante_estimado + ', por pagar ' + e.saliente_estimado : '')));
  }

  function abrirOrden(id) {
    estado.ficha = null;
    return api('GET', '/api/v2/ordenes/' + encodeURIComponent(String(id))).then(function (r) {
      pintarOrden(document.getElementById('ficha'), r.orden);
    }).catch(function (error) { decir(error.message, true); });
  }

  function abrirObjeto(id) {
    estado.ficha = null;
    return api('GET', '/api/v2/objetos/' + encodeURIComponent(String(id))).then(function (r) {
      pintarObjeto(document.getElementById('ficha'), r.objeto);
    }).catch(function (error) { decir(error.message, true); });
  }

  // ---------------------------------------------------------------- arranque

  // Z1: una fuente pasada de su limite sale arriba, antes que la lista: lo que
  // depende de ella esta sin datos, y quien mira tiene que saberlo.
  function pintarFuentes(contenedor, fuentes) {
    vaciar(contenedor);
    fuentes.filter(function (f) { return f.caducada; }).forEach(function (f) {
      anadir(contenedor, el('p', {clase: 'aviso pasada'}, 'Lo último de ' + f.fuente + ' (' +
        f.tipo + ') es del ' + f.exportado + ': ' + f.edad + ' ' + f.unidad +
        ', más que el límite de ' + f.limite + '. Lo que depende de esa fuente está sin datos.'));
    });
  }

  function recargar() {
    api('GET', '/api/v2/fuentes').then(function (r) {
      pintarFuentes(document.getElementById('fuentes'), r.fuentes);
    });
    var lista = api('GET', '/api/v2/facturas').then(function (r) {
      pintarListado(document.getElementById('lista'), r.facturas);
    });
    Promise.all([api('GET', '/api/v2/proveedores'), api('GET', '/api/v2/clientes')]).then(
      function (r) {
        pintarPartes(document.getElementById('partes'), r[0].proveedores, r[1].clientes);
      });
    api('GET', '/api/v2/ordenes').then(function (r) {
      estado.ordenes = r.ordenes;
      pintarOrdenes(document.getElementById('ordenes'), r.ordenes);
    });
    if (estado.ficha !== null) { return lista.then(function () { return abrirFicha(estado.ficha); }); }
    return lista;
  }

  function abrirFicha(id) {
    estado.ficha = id;
    return api('GET', '/api/v2/facturas/' + encodeURIComponent(String(id))).then(function (r) {
      pintarDetalle(document.getElementById('ficha'), r.factura);
    }).catch(function (error) { decir(error.message, true); });
  }

  function entrar(ev) {
    ev.preventDefault();
    estado.token = document.getElementById('token').value;
    api('GET', '/api/v2/yo').then(function (yo) {
      estado.yo = yo;
      var quien = document.getElementById('quien');
      vaciar(quien);
      anadir(quien, yo.nombre + ' (' + yo.permisos.join(', ') + ')');
      return Promise.all([api('GET', '/api/v2/personas'), api('GET', '/api/v2/objetos')]);
    }).then(function (r) {
      estado.personas = r[0].personas;
      estado.objetos = r[1].objetos;
      return recargar();
    }).catch(function (error) { decir(error.message, true); });
  }

  function iniciar() {
    document.getElementById('entrar').addEventListener('submit', entrar);
  }

  window.BMSConsola = {el: el, pintarListado: pintarListado, pintarDetalle: pintarDetalle,
                       pintarPartes: pintarPartes, pintarParte: pintarParte,
                       pintarOrdenes: pintarOrdenes, pintarOrden: pintarOrden,
                       pintarObjeto: pintarObjeto,
                       resumen: resumen, estado: estado};
  document.addEventListener('DOMContentLoaded', iniciar);
})();
"""
