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
  <nav id="navegacion"></nav>
</header>
<main>
  <section id="fuentes"></section>
  <section id="mensaje" role="status"></section>
  <section id="panel"></section>
  <section id="buscar"></section>
  <section id="lista"></section>
  <section id="partes"></section>
  <section id="objetos"></section>
  <section id="ordenes"></section>
  <section id="btw"></section>
  <section id="caja"></section>
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
nav{display:flex;flex-wrap:wrap;gap:.3rem;margin:.4rem 0}
.bloques{display:grid;grid-template-columns:repeat(auto-fill,minmax(22rem,1fr));gap:.6rem}
.bloque{border:1px solid var(--linea);padding:.4rem .6rem}
.enlace{cursor:pointer;text-decoration:underline;margin-right:.4rem}
.fuente{color:var(--suave)}.fuente.manual{color:var(--aten)}
.evento{border-left:3px solid var(--linea);padding-left:.5rem;margin:.3rem 0}
.evento.persona{border-left-color:var(--aten)}
.datos-de-prueba{position:sticky;top:0;z-index:10;background:var(--bloq);color:#fff;
font-weight:700;padding:.45rem .8rem;margin:0 -1rem;text-align:center}
.aislamiento-falla{background:var(--bloq);color:#fff;font-weight:700;padding:.6rem .8rem;
margin:0 -1rem;text-align:center;border-bottom:3px solid #fff}
"""

SCRIPT = r"""
(function () {
  'use strict';

  var estado = {token: null, yo: null, acciones: {}, personas: [], objetos: [], ordenes: [],
                proveedores: [], clientes: [], recursos: [], ficha: null};

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
  var MARCA_CLASE = {'sin resolver': 'discrepancia', 'dudoso': 'dudoso',
                     'verificado': 'verificado', 'corregido a mano': 'atencion',
                     'suplido a mano': 'atencion'};

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

  // Un fichero (el original de una factura, la hoja del BTW) se pide con el token en su
  // cabecera, como todo, y se guarda con el nombre que da el servidor: el token no va
  // nunca en una URL.
  function descargar(ruta, nombre) {
    return fetch(ruta, {headers: {'X-BMS-Token': estado.token || ''}}).then(function (r) {
      if (!r.ok) {
        return r.json().then(function (d) { throw new Error(d.error || ('error ' + r.status)); });
      }
      return r.blob();
    }).then(function (contenido) {
      // El enlace apunta a lo recien descargado (blob:), nunca a algo que venga de un dato.
      var url = URL.createObjectURL(contenido);
      var enlace = el('a', {href: url, download: nombre});
      document.body.appendChild(enlace);
      enlace.click();
      document.body.removeChild(enlace);
      URL.revokeObjectURL(url);
      decir('Descargado: ' + nombre + '.', false);
    }).catch(function (error) { decir('No se descarga: ' + error.message, true); });
  }

  function decir(texto, esError) {
    var caja = document.getElementById('mensaje');
    vaciar(caja);
    anadir(caja, el('p', {clase: esError ? 'error' : ''}, texto));
  }

  // Una orden apuntada sin el efecto pedido (Diferencia.no_vale en servicios.py).
  function noVale(diferencia) {
    var detalle = diferencia.detalle || {};
    return detalle.eficaz === false ? (detalle.motivo_ineficaz || 'no cuenta') : null;
  }

  function resumen(diferencia) {
    if (diferencia.repetida) { return 'Esa petición ya se había aplicado: no se repite.'; }
    if (diferencia.evento_id === null) { return 'No cambia nada.'; }
    var partes = [noVale(diferencia) ?
      'Apuntada (evento ' + diferencia.evento_id + '), pero la verificación NO VALE: ' +
        noVale(diferencia) + '. La cuenta sigue sin verificar y no se puede pagar a ella.' :
      'Hecho (evento ' + diferencia.evento_id + ').'];
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
      decir(resumen(r.diferencia), !!noVale(r.diferencia));
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
      return el('label', {title: c.titulo || ''}, (c.etiqueta || c.nombre) + ' ', entrada);
    });
    var form = el('form', {clase: 'linea', al_enviar: function (ev) {
      ev.preventDefault();
      var datos = {};
      Object.keys(datosFijos).forEach(function (k) { datos[k] = datosFijos[k]; });
      Object.keys(entradas).forEach(function (k) {
        var v = entradas[k].value;
        if (v !== '') { datos[k] = enLista[k] ? [parseInt(v, 10)] : v; }
      });
      if (opciones && opciones.construir) { datos = opciones.construir(datos); }
      ordenar(nombre, datos, peticion);
    }}, hijos, el('button', {type: 'submit'}, textoBoton));
    if (opciones && opciones.titulo) { return el('div', {}, el('span', {clase: 'suave'}, opciones.titulo), form); }
    return form;
  }

  // ---------------------------------------------------------------- lista

  function pintarListado(contenedor, facturas) {
    vaciar(contenedor);
    anadir(contenedor, el('h2', {}, 'Facturas'), tablaFacturas(facturas));
  }

  // Una tabla de facturas (la lista y el resultado de una busqueda), cada fila abre su
  // ficha. Las marcas de edicion manual van en su columna (§11).
  function tablaFacturas(facturas) {
    var cabecera = el('tr', {}, ['Prioridad', 'Puntos', 'Factura', 'Contraparte', 'Total',
      'Vence', 'Pago', 'Revisión', 'Calidad', 'Ediciones', 'Sistema'].map(function (t) {
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
        el('td', {}, f.estado_pago || ''),
        el('td', {}, ETIQUETA_REVISION[f.estado_revision] || ''),
        el('td', {}, f.calidad ? insignia(f.calidad, f.calidad) : ''),
        el('td', {}, ediciones.join(', ')),
        el('td', {}, f.etiqueta, f.motivos && f.motivos.length ?
          el('div', {clase: 'suave'}, f.motivos.join(' · ')) : null));
      anadir(cuerpo, fila);
    });
    return el('table', {}, el('thead', {}, cabecera), cuerpo);
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
      // Paso 12: la fuente (§13) y cada marca de edicion (§11) son una insignia, y de un
      // valor puesto a mano se ve quien, cuando y por que.
      var manual = c.fuente === 'manual_entrada' || c.fuente === 'manual_correccion';
      anadir(cuerpo, el('tr', {},
        el('td', {title: c.campo}, c.etiqueta || c.campo),
        el('td', {}, c.texto === null ? '' : c.texto),
        el('td', {}, original),
        el('td', {}, c.fuente ? insignia(c.fuente_texto || c.fuente,
          'fuente' + (manual ? ' manual' : '')) : ''),
        el('td', {}, c.calidad ? insignia(c.calidad, c.calidad) : ''),
        el('td', {}, marcas.map(function (m) { return insignia(m, MARCA_CLASE[m] || ''); }),
          c.cambiado_por && c.editado ?
          el('div', {clase: 'suave'}, (c.cambiado_por) + ', ' + (c.cambiado_en || '') +
            (c.motivo ? ': «' + c.motivo + '»' : '')) : null),
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
      var recursos = [['', '(sin persona)']].concat(estado.recursos.map(function (r) {
        return [String(r.id), r.nombre + (r.activo ? '' : ' (inactivo)')]; }));
      var activas = l.imputaciones.filter(function (imp) { return !imp.retirada; });
      l.imputaciones.forEach(function (imp) {
        if (imp.retirada) { return; }
        anadir(caja, el('div', {clase: 'caja'}, 'Imputación ' + imp.id + ': ',
          imp.objeto || '(sin Objeto)', ' · ', imp.recurso || '(sin persona)', ' · PO ',
          imp.orden_compra || '(ninguna)', ' · ', imp.importe || '', imp.horas ?
            ' · ' + imp.horas + ' h' : '',
          formulario('cambiar_objeto', [{nombre: 'objeto_id', etiqueta: 'Objeto', opciones: objetos},
            {nombre: 'recurso_id', etiqueta: 'persona', opciones: recursos},
            {nombre: 'motivo', etiqueta: 'motivo'}], {imputacion_id: imp.id, rev: imp.rev},
            'Cambiar imputación'),
          formulario('imputar_po', [{nombre: 'orden_compra_id', etiqueta: 'PO', opciones: ordenes},
            {nombre: 'motivo', etiqueta: 'motivo'}], {imputacion_id: imp.id, rev: imp.rev},
            'Imputar a la PO')));
      });
      if (!l.retirada) {
        anadir(caja, formulario('excluir_linea', [{nombre: 'motivo', etiqueta: 'motivo'}],
          {linea_id: l.id, rev: l.rev}, 'Excluir la línea'),
          formularioReparto(l, objetos, activas));
      }
    });
    anadir(caja, el('h3', {}, 'Añadir una línea que está en el papel'),
      formulario('anadir_linea', [{nombre: 'descripcion_doc', etiqueta: 'descripción'},
        {nombre: 'cantidad_mil', etiqueta: 'cantidad'}, {nombre: 'tarifa_e4', etiqueta: 'tarifa'},
        {nombre: 'importe_cent', etiqueta: 'importe'}, {nombre: 'motivo', etiqueta: 'motivo'}],
        {factura_id: f.id, rev: f.rev}, 'Añadir la línea', {construir: function (d) {
          var valores = {};
          ['descripcion_doc', 'cantidad_mil', 'tarifa_e4', 'importe_cent'].forEach(function (k) {
            if (d[k] !== undefined) { valores[k] = d[k]; delete d[k]; }
          });
          d.valores = valores;
          return d;
        }}));
    return caja;
  }

  // Repartir una linea entre Objetos: hasta tres partes, que tienen que sumar la linea (I1
  // lo vigila despues, si la linea se corrige).
  function formularioReparto(l, objetos, activas) {
    var campos = [];
    [1, 2, 3].forEach(function (n) {
      campos.push({nombre: 'objeto_' + n, etiqueta: 'Objeto ' + n, opciones: objetos});
      campos.push({nombre: 'importe_' + n, etiqueta: 'importe ' + n});
      campos.push({nombre: 'horas_' + n, etiqueta: 'horas ' + n});
    });
    campos.push({nombre: 'motivo', etiqueta: 'motivo'});
    return formulario('dividir_linea', campos, {linea_id: l.id, rev: l.rev},
      activas.length > 1 ? 'Volver a repartir' : 'Repartir entre Objetos', {
        titulo: 'Repartir la línea ' + l.orden + ' (las partes suman la línea)',
        construir: function (d) {
          var partes = [];
          [1, 2, 3].forEach(function (n) {
            var importe = d['importe_' + n];
            if (importe !== undefined) {
              var parte = {objeto_id: d['objeto_' + n] ? parseInt(d['objeto_' + n], 10) : null,
                           importe: importe};
              if (d['horas_' + n] !== undefined) { parte.horas = d['horas_' + n]; }
              partes.push(parte);
            }
            delete d['objeto_' + n]; delete d['importe_' + n]; delete d['horas_' + n];
          });
          d.partes = partes;
          return d;
        }});
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
      textoVencimiento(f.vencimiento),
      pintarOriginal(f),
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
      el('h3', {}, 'Pagos'), pintarPagos(f),
      el('h3', {}, 'Anular o fusionar'), pintarAnular(f),
      el('h3', {}, 'Referencias (PO, orden, proyecto)'), pintarReferencias(f),
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
      el('div', {id: 'historia-' + f.id},
        el('ul', {}, f.historia.map(function (h) {
          return el('li', {}, h.en + ' ' + h.tipo + (h.usuario ? ' (' + h.usuario + ')' : '') +
            (h.motivo ? ': ' + h.motivo : ''));
        }))));
  }

  // De donde sale el vencimiento (§13): el impreso, o la fecha mas el plazo; del maestro si
  // el plazo es el acordado con la parte.
  function textoVencimiento(v) {
    if (!v || !v.fecha) { return el('p', {clase: 'suave'}, 'Sin vencimiento: ni impreso ni ' +
      'plazo con que calcularlo.'); }
    return el('p', {}, 'Vence el ' + v.fecha + (v.fuente_texto ? ' · ' + v.fuente_texto : '') +
      (v.plazo_dias !== null && v.plazo_dias !== undefined ? ' (plazo de ' + v.plazo_dias +
        ' días' + (v.fuente_ref ? ', ' + v.fuente_ref : '') + ')' : ''));
  }

  function pintarOriginal(f) {
    var o = f.original;
    if (!o) { return el('p', {clase: 'suave'}, 'Sin documento: llegó de otro sistema.'); }
    if (!o.guardado) { return el('p', {clase: 'aviso'}, 'El original de ' + (o.nombre || '') +
      ' no está en el almacén (Q4).'); }
    return el('p', {}, 'Original: ' + (o.nombre || o.sha256.slice(0, 12)) + ' ',
      el('button', {type: 'button', al_pulsar: function () {
        descargar('/api/v2/facturas/' + encodeURIComponent(String(f.id)) + '/original',
                  o.nombre || ('factura-' + f.id + '.pdf'));
      }}, 'Descargar el original'),
      el('span', {clase: 'suave'}, ' (queda apuntado quién lo abre)'));
  }

  function pintarPagos(f) {
    var caja = el('div');
    (f.pagos || []).forEach(function (a) {
      var acciones = [];
      if (a.estado === 'propuesta') {
        acciones.push(formulario('confirmar_pago', [{nombre: 'motivo', etiqueta: 'nota'}],
          {aplicacion_id: a.id, rev: a.rev}, 'Confirmar el pago'));
      }
      if (a.estado !== 'retirada' && a.fuente !== 'exact') {
        acciones.push(formulario('retirar_pago', [{nombre: 'motivo', etiqueta: 'motivo'}],
          {aplicacion_id: a.id, rev: a.rev}, 'Retirar'));
      }
      anadir(caja, el('div', {clase: 'caja'}, el('strong', {}, a.importe + ' el ' + a.fecha_pago),
        ' · ' + a.fuente + ' · ' + a.estado + (a.movimiento_id ? ' · movimiento ' +
          a.movimiento_id : '') + (a.contraparte ? ' · ' + a.contraparte : ''),
        a.concepto ? el('div', {clase: 'suave'}, a.concepto) : null, acciones));
    });
    if (!(f.pagos || []).length) { anadir(caja, el('p', {clase: 'suave'}, 'Ningún pago apuntado.')); }
    if (!f.anulada && f.fusionada_en_id === null) {
      anadir(caja, formulario('marcar_pagada', [
        {nombre: 'importe', etiqueta: 'importe', titulo: 'por defecto, lo que queda'},
        {nombre: 'fecha_pago', etiqueta: 'pagada el', tipo: 'date'},
        {nombre: 'movimiento_id', etiqueta: 'movimiento del banco (id)'},
        {nombre: 'evidencia_documento_id', etiqueta: 'documento que lo prueba (id)'},
        {nombre: 'motivo', etiqueta: 'motivo'}], {factura_id: f.id, rev: f.rev},
        'Apuntar un pago ya hecho', {titulo: 'No paga nada: apunta lo que ya se pagó.'}));
    }
    return caja;
  }

  function pintarAnular(f) {
    if (f.fusionada_en_id !== null) {
      return el('div', {}, el('p', {}, 'Fusionada en la factura ', enlaceFactura(f.fusionada_en_id)),
        formulario('deshacer_fusion', [{nombre: 'motivo', etiqueta: 'motivo'}],
          {factura_id: f.id, rev: f.rev}, 'Deshacer la fusión'));
    }
    if (f.anulada) { return el('p', {clase: 'suave'}, 'Anulada: no se paga ni se cuenta.'); }
    return el('div', {},
      formulario('anular_factura', [{nombre: 'motivo', etiqueta: 'motivo'}],
        {factura_id: f.id, rev: f.rev}, 'Anular la factura',
        {titulo: 'Con un pago apuntado no se anula: se retira el pago o se apunta un abono.'}),
      formulario('fusionar_factura', [{nombre: 'destino_id', etiqueta: 'es un reenvío de (id)'},
        {nombre: 'motivo', etiqueta: 'motivo'}], {factura_id: f.id, rev: f.rev},
        'Fusionar en esa factura'));
  }

  var CLASES_REFERENCIA = [['po', 'PO'], ['orden', 'orden'], ['proyecto', 'proyecto'],
    ['ref_cliente', 'referencia del cliente'], ['otra', 'otra']];

  function pintarReferencias(f) {
    return el('div', {},
      el('ul', {}, (f.referencias || []).filter(function (r) { return !r.retirada; }).map(
        function (r) {
          return el('li', {}, (r.etiqueta ? r.etiqueta + ': ' : '') + r.valor + ' (' + r.clase +
            ')', formulario('cambiar_po', [{nombre: 'clase', etiqueta: 'es', opciones:
              CLASES_REFERENCIA}, {nombre: 'motivo', etiqueta: 'motivo'}],
              {referencia_id: r.id, rev: r.rev}, 'Cambiar'));
        })),
      formulario('anadir_referencia', [{nombre: 'valor', etiqueta: 'referencia'},
        {nombre: 'etiqueta', etiqueta: 'como la llama el papel'},
        {nombre: 'clase', etiqueta: 'es', opciones: CLASES_REFERENCIA},
        {nombre: 'motivo', etiqueta: 'motivo'}], {factura_id: f.id, rev: f.rev},
        'Añadir una referencia'));
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
      v.ibanes ? pintarCuentas(v) : null,
      el('h3', {}, 'Corregir los datos'), pintarCorregirMaestro(tabla, v),
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

  // Paso 5 y revision final: el registro de cuentas de un proveedor y lo que se hace con el
  // desde aqui. Una cuenta se teclea (se lee al telefono), nunca se copia de la factura, y se
  // llama al telefono del maestro, no al de ningun documento.
  function pintarCuentas(v) {
    var registro = v.ibanes.registro;
    var fijos = {proveedor_id: v.id};
    return el('div', {}, el('h3', {}, 'Cuentas'),
      el('p', {}, 'Teléfono de verificación (el del maestro, al que se llama): ' +
        (v.telefono_verificacion || 'ninguno: sin él no se puede verificar una cuenta')),
      filas(['IBAN', 'Estado', 'Pagable', 'En Exact'], registro.map(function (c) {
        return [c.iban, c.estado, c.pagable ? 'sí' : 'no', c.en_exact ? 'sí' : 'no']; })),
      filas(['IBAN impreso', 'En el registro', 'Primera', 'Última', 'Facturas'],
        v.ibanes.impresos.map(function (i) {
          return [i.iban, i.en_el_registro ? 'sí' : 'no (F3: por verificar)', i.primera,
            i.ultima, i.facturas]; })),
      el('p', {clase: 'suave'}, 'Verificar no basta para pagar: la cuenta tiene que estar ' +
        'también en el último maestro de Exact (F2). Cámbiala en Exact, exporta los ' +
        'acreedores e impórtalos.'),
      formulario('verificar_iban', [
        {nombre: 'iban', etiqueta: 'IBAN (tecleado)'},
        {nombre: 'telefono', etiqueta: 'teléfono llamado'},
        {nombre: 'persona_contactada', etiqueta: 'quién lo confirmó'},
        {nombre: 'factura_id', etiqueta: 'factura que la trajo (id)'},
        {nombre: 'nota', etiqueta: 'nota'}, {nombre: 'motivo', etiqueta: 'motivo'}], fijos,
        'Verificar por teléfono'),
      formulario('rechazar_iban', [
        {nombre: 'iban', etiqueta: 'IBAN (tecleado)'},
        {nombre: 'factura_id', etiqueta: 'factura que la trajo (id)'},
        {nombre: 'decision_facturas', etiqueta: 'esa factura', opciones: [['', '(nada)'],
          ['pagar_a_verificada', 'se paga a la verificada'], ['anular', 'se anula']]},
        {nombre: 'telefono', etiqueta: 'teléfono llamado'},
        {nombre: 'motivo', etiqueta: 'motivo'}], fijos, 'Rechazar la cuenta'),
      formulario('atestar_iban', [
        {nombre: 'iban', etiqueta: 'IBAN (vacío: todas las heredadas)'},
        {nombre: 'nota', etiqueta: 'nota'}, {nombre: 'motivo', etiqueta: 'motivo'}], fijos,
        'Atestar lo heredado (F0)'),
      formulario('fijar_telefono_verificacion', [
        {nombre: 'telefono', etiqueta: 'teléfono nuevo', valor: v.telefono_verificacion},
        {nombre: 'motivo', etiqueta: 'motivo'}], {proveedor_id: v.id, rev: v.rev},
        'Cambiar el teléfono', {titulo: 'Cambiarlo abre el enfriamiento (F9).'}));
  }

  function pintarCorregirMaestro(tabla, v) {
    var corregibles = v.corregibles || [];
    if (!corregibles.length) { return el('p', {clase: 'suave'}, 'Lo de esta ficha viene de ' +
      'Exact o de TRNSPRNT: se corrige allí y lo trae la siguiente importación.'); }
    return formulario('corregir_maestro', [
      {nombre: 'campo', etiqueta: 'campo', opciones: corregibles.map(function (c) {
        return [c.campo, c.etiqueta + (c.texto ? ' (' + c.texto + ')' : '')]; })},
      {nombre: 'valor', etiqueta: 'valor'}, {nombre: 'motivo', etiqueta: 'motivo'}],
      {tabla: tabla === 'proveedores' ? 'proveedor' : 'cliente', fila_id: v.id, rev: v.rev},
      'Corregir');
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
      el('table', {}, el('thead', {}, cabecera), cuerpo), formularioPo());
  }

  // Registrar una PO: de un cliente (lo que BMS puede facturar) o a un proveedor.
  function formularioPo() {
    var partes = [['', '(elige)']].concat(estado.clientes.map(function (c) {
      return ['cliente:' + c.id, 'de ' + c.nombre + ' (cliente)']; })).concat(
      estado.proveedores.map(function (p) {
        return ['proveedor:' + p.id, 'a ' + p.nombre + ' (proveedor)']; }));
    var objetos = [['', '(cualquiera de la parte)']].concat(estado.objetos.map(function (o) {
      return [String(o.id), o.codigo]; }));
    return el('div', {}, el('h3', {}, 'Registrar una orden de compra'),
      formulario('registrar_po', [{nombre: 'numero', etiqueta: 'número'},
        {nombre: 'parte', etiqueta: 'parte', opciones: partes},
        {nombre: 'valor', etiqueta: 'valor sin IVA'},
        {nombre: 'fecha_inicio', etiqueta: 'desde', tipo: 'date'},
        {nombre: 'fecha_fin', etiqueta: 'hasta', tipo: 'date'},
        {nombre: 'objetos', etiqueta: 'Objeto', opciones: objetos, lista: true},
        {nombre: 'motivo', etiqueta: 'motivo'}], {}, 'Registrar', {construir: function (d) {
          var parte = (d.parte || ':').split(':');
          delete d.parte;
          d.lado = parte[0];
          d.parte_id = parte[1] ? parseInt(parte[1], 10) : null;
          return d;
        }}));
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
      formulario('corregir_po', [{nombre: 'campo', etiqueta: 'corregir', opciones: [
        ['fecha_emision', 'fecha de emisión'], ['fecha_inicio', 'fecha de inicio'],
        ['documento_id', 'documento (id)']]}, {nombre: 'valor', etiqueta: 'valor'},
        {nombre: 'motivo', etiqueta: 'motivo'}], {orden_compra_id: o.id, rev: o.rev},
        'Corregir la PO'),
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
        h.planning === 'caducado' ? 'El planning está pasado de su frescura (Z1): puede no ' +
        'ser el de hoy. Una semana que no cubre dice «-», no cero.' :
        'Sin planning importado: solo las horas facturadas.'),
      filas(['Semana', 'Planificadas', 'Validadas', 'Proveedores', 'Cliente', 'Sin facturar',
        'Dif. proveedor', 'Dif. cliente'], semanas.map(function (f) {
          return [f.semana, f.planificadas || '-', f.validadas || '-', f.proveedor || '-',
            f.cliente || '-', f.sin_facturar || '-', f.diferencia_proveedor || '-',
            f.diferencia_cliente || '-']; })),
      el('p', {}, 'Esperado: por cobrar ' + e.entrante + ' · por pagar ' + e.saliente +
        (e.entrante_estimado !== null ? ' · estimado aparte: por cobrar ' +
          e.entrante_estimado + ', por pagar ' + e.saliente_estimado : '')),
      v.economia ? pintarEconomia(v.economia) : null,
      v.facturas ? el('div', {}, el('h3', {}, 'Facturas de venta'),
        tablaDeObjeto(v.facturas.salientes),
        el('h3', {}, 'Facturas de compra'), tablaDeObjeto(v.facturas.entrantes)) : null,
      el('h3', {}, 'Otro nombre con que lo imprimen las facturas'),
      formulario('anadir_alias', [{nombre: 'alias', etiqueta: 'alias'}],
        {tabla: 'objeto', fila_id: v.id}, 'Añadir el alias'));
  }

  // Paso 12: ingresos, costes y margen del Objeto (§5), sin IVA.
  function pintarEconomia(eco) {
    var fila = function (nombre, b) {
      return [nombre, b.ingresos, b.costes, b.margen, b.margen_pct || '-'];
    };
    return el('div', {},
      el('h3', {}, 'Ingresos, costes y margen (sin IVA)'),
      filas(['', 'Ingresos', 'Costes', 'Margen', '%'], [
        fila('Del ' + eco.periodo.desde + ' al ' + eco.periodo.hasta, eco.periodo),
        fila('Año ' + eco.ano.ano, eco.ano), fila('De siempre', eco.siempre)]),
      el('h3', {}, 'Por mes (fecha de factura)'),
      filas(['Mes', 'Ingresos', 'Costes', 'Margen', '%'], eco.por_mes.map(function (m) {
        return fila(m.mes, m); })),
      el('h3', {}, 'Por semana (días de trabajo)'),
      filas(['Semana', 'Ingresos', 'Costes', 'Margen', '%'], eco.por_semana.map(function (m) {
        return fila(m.semana, m); })));
  }

  function tablaDeObjeto(lista) {
    if (!lista.length) { return el('p', {clase: 'suave'}, 'Ninguna.'); }
    return el('table', {}, el('tbody', {}, lista.map(function (f) {
      return el('tr', {clase: 'fila', al_pulsar: function () { abrirFicha(f.id); }},
        el('td', {}, f.fecha_factura || ''), el('td', {}, f.numero || '(sin número)'),
        el('td', {}, f.contraparte || ''), el('td', {}, f.importe_objeto),
        el('td', {}, f.horas || ''), el('td', {}, (f.estado_pago || '') +
          (f.cuenta ? '' : ' (no cuenta)')));
    })));
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

  // ---------------------------------------------------------------- paso 12: panel (§17)

  var NOMBRE_VENTANA = {vencido: 'Vencido', semana: 'Esta semana', mes: 'Este mes',
                        proximos_30: 'Próximos 30 días', periodo: 'El periodo pedido',
                        sin_fecha: 'Sin fecha', total: 'Total'};

  function enlaceFactura(id, texto) {
    return el('span', {clase: 'enlace', al_pulsar: function () { abrirFicha(id); }},
      texto || ('#' + id));
  }

  function bloque(titulo) {
    var caja = el('div', {clase: 'bloque'}, el('h3', {}, titulo));
    for (var i = 1; i < arguments.length; i++) { poner(caja, arguments[i]); }
    return caja;
  }

  function bloqueDinero(titulo, b) {
    return bloque(titulo, filas(['', 'Importe'], [
      ['Pendiente (' + b.facturas + ' facturas)', b.pendiente],
      ['Vencido (' + b.vencidas + ')', b.vencido], ['Esta semana', b.semana],
      ['Este mes', b.mes], ['Próximos 30 días', b.proximos_30], ['Sin fecha', b.sin_fecha]]));
  }

  function textoEstimado(e) {
    if (e.importe_cent === null) { return e.nota; }
    return 'Estimado del planning (aparte): por cobrar ' + e.entrada_sin_facturar +
      ' sin facturar y ' + e.entrada_planificada + ' planificado; por pagar ' +
      e.salida_sin_facturar + ' y ' + e.salida_planificada + '. ' + e.nota;
  }

  function bloqueFacturacion(f) {
    if (f.estado !== 'ok') { return bloque('Facturación', el('p', {clase: 'suave'}, f.detalle)); }
    return bloque('Facturación',
      el('p', {}, 'Trabajo sin facturar: ' + f.sin_facturar.valor + ' (' +
        f.sin_facturar.horas + ' h en ' + f.sin_facturar.periodos + ' periodos' +
        (f.sin_facturar.estimado ? ', en parte estimado' : '') + ')'),
      el('p', {}, 'Periodos sin factura: ' + f.periodos_sin_factura.length),
      el('ul', {}, f.periodos_sin_factura.map(function (x) {
        return el('li', {}, 'cliente ' + x.cliente_id + ': del ' + x.desde + ' al ' + x.hasta);
      })),
      el('p', {}, 'Horas validadas fuera de una venta de su periodo: ' +
        f.horas_sin_facturar.length),
      el('ul', {}, f.horas_sin_facturar.map(function (x) {
        return el('li', {}, el('span', {clase: 'enlace', al_pulsar: function () {
          abrirFicha(x.factura_id); }}, 'factura ' + x.factura_id),
          ': ' + x.horas + ' h del ' + x.desde + ' al ' + x.hasta +
          (x.valor ? ' (' + x.valor + (x.estimado ? ', estimado' : '') + ')' : ''));
      })),
      el('p', {}, 'Diferencias con el planning: ' + f.diferencias_planning.hallazgos +
        ' (' + f.diferencias_planning.facturas + ' facturas, ' + f.diferencias_planning.valor +
        ')'));
  }

  function listaPo(titulo, lista) {
    if (!lista.length) { return null; }
    return el('div', {}, el('span', {clase: 'suave'}, titulo + ': '), lista.map(function (o) {
      return el('span', {clase: 'enlace', al_pulsar: function () { abrirOrden(o.id); }},
        o.numero + ' (' + o.consumido_pct + ', fin ' + (o.fecha_fin || '-') + ')');
    }));
  }

  function bloquePo(po) {
    // Los dos lados no se suman: lo que BMS puede facturar y lo que le pueden facturar.
    function lado(titulo, c) {
      return [titulo, String(c.activas), c.valor, c.consumido, c.restante];
    }
    return bloque('Órdenes de compra',
      filas(['Activas (sin IVA)', 'PO', 'Valor', 'Consumido', 'Queda'], [
        lado('De clientes (lo que BMS puede facturar)', po.cliente),
        lado('De proveedores (lo que pueden facturar a BMS)', po.proveedor)]),
      listaPo('Cerca de su límite', po.cerca_del_limite),
      listaPo('Cerca de caducar', po.cerca_de_caducar),
      listaPo('Ya caducadas, con aviso', po.caducadas),
      listaPo('Se agotan antes de su fin', po.agotamiento_previsto));
  }

  function bloqueBtw(b) {
    var plazo = b.proximo_plazo;
    return bloque('BTW ' + b.trimestre + ' (' + b.estado + ')',
      filas(['', 'Importe'], [['Ingresos sin IVA', b.ingresos],
        ['IVA repercutido y autoliquidado (5a)', b.iva_repercutido],
        ['IVA deducible (5b)', b.iva_deducible], ['Saldo (5c)', b.saldo]]),
      el('p', {}, plazo ? 'Próximo plazo: ' + plazo.trimestre + ', el ' +
        plazo.limite_presentacion + ' (' + plazo.dias_para_limite + ' días)' :
        'Ningún plazo por venir sin presentar.'),
      b.plazos_pasados.length ? el('p', {clase: 'pasada'}, 'Plazo pasado sin la presentación ' +
        'anotada: ' + b.plazos_pasados.join(', ')) : null,
      b.configuracion_confirmada ? null : el('p', {clase: 'suave'},
        'La configuración del BTW está por confirmar con el asesor.'),
      el('span', {clase: 'enlace', al_pulsar: function () { abrirTrimestre(b.trimestre); }},
        'Ver el trimestre'));
  }

  function bloqueVencidas(titulo, v) {
    return bloque(titulo + ': ' + v.facturas + ' (' + v.pendiente + ')',
      v.lista.length ? el('table', {}, el('tbody', {}, v.lista.map(function (f) {
        return el('tr', {clase: 'fila', al_pulsar: function () { abrirFicha(f.id); }},
          el('td', {}, f.numero || '(sin número)'), el('td', {}, f.contraparte || ''),
          el('td', {}, f.vencimiento || ''), el('td', {}, (f.dias === null ? '' : f.dias + ' días')),
          el('td', {}, f.pendiente || ''));
      }))) : el('p', {clase: 'suave'}, 'Ninguna.'));
  }

  function bloqueAtencion(a) {
    return el('div', {},
      el('p', {}, a.bloqueadas + ' facturas bloqueadas, ' + a.urgentes + ' urgentes, ' +
        a.atencion + ' en atención · ' + a.excepciones.abiertas + ' excepciones abiertas · ' +
        a.hallazgos + ' avisos activos (' + a.aceptados + ' aceptados)'),
      el('div', {clase: 'bloques'},
        bloqueVencidas('Compras vencidas', a.compras_vencidas),
        bloqueVencidas('Ventas vencidas', a.ventas_vencidas),
        a.categorias.filter(function (c) { return c.activos || c.aceptados; }).map(function (c) {
          return bloque(c.titulo + ': ' + c.activos,
            el('p', {clase: 'suave'}, Object.keys(c.reglas).map(function (r) {
              return r + ' ' + c.reglas[r]; }).join(' · ') +
              (c.aceptados ? ' · ' + c.aceptados + ' aceptados' : '')),
            el('div', {}, c.factura_ids.map(function (id) { return enlaceFactura(id); })));
        })));
  }

  function pintarPanel(contenedor, p) {
    vaciar(contenedor);
    var caja = p.caja;
    anadir(contenedor, el('h2', {}, 'Panel a ' + p.hoy),
      p.al_dia ? null : el('p', {clase: 'aviso pasada'}, 'El estado de las facturas es del ' +
        p.estado_del + ': falta la pasada de hoy (bms-agent recalcular --diaria; en el ' +
        'entorno de Docker la hacen iniciar.bat e importar.bat).'),
      el('div', {clase: 'bloques'},
        bloqueDinero('Entra (cobros)', p.dinero_entra),
        bloqueDinero('Sale (pagos)', p.dinero_sale),
        bloque('Caja',
          filas(['', 'Entra', 'Sale', 'Neto'], ['vencido', 'semana', 'mes', 'proximos_30',
            'total'].map(function (v) {
              var x = caja.ventanas[v];
              return [NOMBRE_VENTANA[v], x.entrada, x.salida, x.neto]; })),
          el('p', {clase: 'suave'}, 'Movido por el banco este mes: cobrado ' + caja.cobrado_mes +
            ', pagado ' + caja.pagado_mes),
          el('p', {clase: 'suave'}, textoEstimado(caja.estimado))),
        bloqueFacturacion(p.facturacion), bloquePo(p.ordenes_compra), bloqueBtw(p.btw)),
      el('h3', {}, 'Requiere atención'), bloqueAtencion(p.atencion));
  }

  // ---------------------------------------------------------------- paso 12: busqueda (§18)

  // Los selectores de una parte salen de las listas que ya tiene la consola.
  function opcionesDe(nombre) {
    var vacio = [['', '(cualquiera)']];
    if (nombre === 'proveedor_id') { return vacio.concat(estado.proveedores.map(function (p) {
      return [String(p.id), p.nombre]; })); }
    if (nombre === 'cliente_id') { return vacio.concat(estado.clientes.map(function (p) {
      return [String(p.id), p.nombre]; })); }
    if (nombre === 'objeto_id') { return vacio.concat(estado.objetos.map(function (o) {
      return [String(o.id), o.codigo]; })); }
    if (nombre === 'orden_compra_id') { return vacio.concat(estado.ordenes.map(function (o) {
      return [String(o.id), o.numero]; })); }
    return null;
  }

  function entradaDeFiltro(f) {
    var opciones = opcionesDe(f.nombre);
    if (!opciones && f.tipo === 'lista') {
      opciones = [['', '(cualquiera)']].concat(f.valores.map(function (v) { return [v, v]; }));
    }
    if (!opciones && f.tipo === 'si_no') { opciones = [['', '(da igual)'], ['si', 'sí'], ['no', 'no']]; }
    if (opciones) {
      var lista = el('select', {name: f.nombre});
      opciones.forEach(function (o) { anadir(lista, el('option', {valor: o[0]}, o[1])); });
      return lista;
    }
    return el('input', {name: f.nombre, type: f.tipo === 'fecha' ? 'date' : 'text',
                        placeholder: f.tipo === 'trimestre' ? '2026-T3' : ''});
  }

  function pintarBuscador(contenedor, filtros) {
    vaciar(contenedor);
    var entradas = {};
    var resultado = el('div');
    var orden = el('select', {name: 'orden'});
    ['prioridad', 'fecha', 'vencimiento', 'importe', 'numero'].forEach(function (o) {
      anadir(orden, el('option', {valor: o}, o)); });
    var form = el('form', {clase: 'linea', al_enviar: function (ev) {
      ev.preventDefault();
      var partes = [];
      Object.keys(entradas).forEach(function (k) {
        var v = entradas[k].value;
        if (v !== '') { partes.push(encodeURIComponent(k) + '=' + encodeURIComponent(v)); }
      });
      partes.push('orden=' + encodeURIComponent(orden.value));
      api('GET', '/api/v2/buscar?' + partes.join('&')).then(function (r) {
        pintarBusqueda(resultado, r.busqueda);
      }).catch(function (error) { decir('No se puede buscar: ' + error.message, true); });
    }}, filtros.map(function (f) {
      entradas[f.nombre] = entradaDeFiltro(f);
      return el('label', {title: f.descripcion}, f.nombre + ' ', entradas[f.nombre]);
    }), el('label', {}, 'orden ', orden), el('button', {type: 'submit'}, 'Buscar'));
    anadir(contenedor, el('h2', {}, 'Buscar facturas'), form, resultado);
  }

  function textoSuma(r) {
    // Solo suman las que cuentan, y compras y ventas por separado.
    var s = r.suma;
    function cifras(c) {
      return 'suman ' + c.total + ', base ' + c.base + ', pendiente ' + c.pendiente;
    }
    var texto = r.total + ' factura(s)' + (r.total > r.facturas.length ?
      ' (se ven ' + r.facturas.length + ')' : '');
    if (s.mezcla) {
      texto += ': compras (' + s.compras.facturas + ') ' + cifras(s.compras) +
        '; ventas (' + s.ventas.facturas + ') ' + cifras(s.ventas);
    } else {
      texto += ': ' + cifras(s);
    }
    if (s.no_cuentan) {
      texto += '. ' + s.no_cuentan + ' no cuentan (anuladas, copias o sustituidas) y no suman';
    }
    return texto + '.';
  }

  function pintarBusqueda(contenedor, r) {
    vaciar(contenedor);
    anadir(contenedor,
      el('p', {}, textoSuma(r)),
      r.al_dia ? null : el('p', {clase: 'aviso pasada'}, 'El estado es del ' + r.estado_del +
        ': falta la pasada de hoy.'),
      tablaFacturas(r.facturas));
  }

  // ---------------------------------------------------------------- paso 12: Objetos (§5)

  function pintarObjetos(contenedor, r) {
    vaciar(contenedor);
    var cuerpo = el('tbody');
    r.objetos.forEach(function (o) {
      anadir(cuerpo, el('tr', {clase: 'fila', al_pulsar: function () { abrirObjeto(o.id); }},
        el('td', {}, o.codigo), el('td', {}, o.cliente || ''),
        el('td', {}, o.siempre.ingresos), el('td', {}, o.siempre.costes),
        el('td', {}, o.siempre.margen), el('td', {}, o.siempre.margen_pct || '-'),
        el('td', {}, o.ano.ingresos), el('td', {}, o.ano.margen)));
    });
    var sin = r.sin_objeto.total;
    anadir(cuerpo, el('tr', {}, el('td', {}, '(sin Objeto)'), el('td', {}, ''),
      el('td', {}, sin.ingresos), el('td', {}, sin.costes), el('td', {}, sin.margen),
      el('td', {}, ''), el('td', {}, ''), el('td', {}, '')));
    var cabecera = el('tr', {}, ['Objeto', 'Cliente', 'Ingresos', 'Costes', 'Margen', '%',
      'Ingresos ' + r.ano, 'Margen ' + r.ano].map(function (t) { return el('th', {}, t); }));
    anadir(contenedor, el('h2', {}, 'Objetos'),
      el('table', {}, el('thead', {}, cabecera), cuerpo),
      el('p', {clase: 'suave'}, 'Base de todas las ventas ' + r.totales.ingresos +
        ' y de todas las compras ' + r.totales.costes + ', sin IVA' +
        (r.totales.sin_base ? '; ' + r.totales.sin_base + ' factura(s) sin base o en otra ' +
          'moneda no suman hasta que se corrigen.' : '.')));
  }

  // ---------------------------------------------------------------- paso 12: BTW

  function pintarBtw(contenedor, b) {
    vaciar(contenedor);
    var fila = function (t) {
      return el('tr', {clase: 'fila', al_pulsar: function () { abrirTrimestre(t.etiqueta); }},
        el('td', {}, t.etiqueta), el('td', {}, t.estado), el('td', {}, t.limite_presentacion),
        el('td', {}, String(t.dias_para_limite)));
    };
    var a = b.actual;
    anadir(contenedor, el('h2', {}, 'BTW'),
      b.configuracion.confirmada ? null : el('p', {clase: 'aviso'},
        'La configuración del BTW está por confirmar con el asesor.'),
      el('table', {}, el('thead', {}, el('tr', {}, ['Trimestre', 'Estado', 'Plazo', 'Días']
        .map(function (t) { return el('th', {}, t); }))),
        el('tbody', {}, [fila(a)].concat(b.anteriores.map(fila)))),
      el('p', {clase: 'suave'}, 'Nada aquí presenta la declaración: se presenta a mano en el ' +
        'portal de la Belastingdienst y aquí se anota.'));
  }

  function pintarTrimestre(contenedor, t) {
    vaciar(contenedor);
    var c = t.cifras;
    anadir(contenedor,
      el('h2', {}, 'BTW ' + t.etiqueta + ' — ' + t.estado),
      el('p', {}, 'Del ' + t.inicio + ' al ' + t.fin + ' · presentar y pagar antes del ' +
        t.limite_presentacion + ' (' + t.dias_para_limite + ' días)' +
        (t.referencia ? ' · presentado el ' + t.presentado_en + ' por ' + t.presentado_por +
          ', referencia ' + t.referencia : '')),
      filas(['Rúbrica', '', 'Base', 'IVA'], c.rubricas.map(function (r) {
        return [r.rubrica, r.descripcion, importe(r.omzet_cent), importe(r.btw_cent)]; })),
      filas(['', 'Importe'], [['5a', importe(c['5a'])], ['5b', importe(c['5b'])],
        ['5c (a pagar; negativo, a devolver)', importe(c['5c'])]]),
      el('h3', {}, 'Facturas que piden revisar el IVA'),
      t.revisar.length ? el('table', {}, el('tbody', {}, t.revisar.map(function (x) {
        return el('tr', {clase: 'fila', al_pulsar: function () { abrirFicha(x.factura_id); }},
          el('td', {}, x.numero || '(sin número)'), el('td', {}, x.contraparte || ''),
          el('td', {}, x.reglas.join(', ')), el('td', {}, x.fuera_de_las_cifras || ''));
      }))) : el('p', {clase: 'suave'}, 'Ninguna.'),
      t.diferencias.length ? el('div', {}, el('h3', {}, 'Diferencias con lo presentado'),
        filas(['Factura', 'Motivo'], t.diferencias.map(function (d) {
          return [d.factura_id, d.motivo]; }))) : null,
      el('h3', {}, 'Estado'),
      t.estado === 'abierto' && t.terminado ? formulario('btw_lista_para_revision',
        [{nombre: 'motivo', etiqueta: 'motivo'}],
        {trimestre: t.etiqueta, hoja_sha256: t.hoja_sha256}, 'Marcar lista para revisar') : null,
      t.estado === 'listo_revision' ? formulario('btw_reabrir',
        [{nombre: 'motivo', etiqueta: 'motivo'}], {trimestre: t.etiqueta, rev: t.rev},
        'Reabrir') : null,
      t.estado === 'listo_revision' ? formulario('btw_anotar_presentacion', [
        {nombre: 'referencia', etiqueta: 'referencia del acuse'},
        {nombre: 'importe_declarado', etiqueta: 'importe declarado'},
        {nombre: 'fecha_presentacion', etiqueta: 'presentada el', tipo: 'date'},
        {nombre: 'motivo', etiqueta: 'motivo'}],
        {trimestre: t.etiqueta, rev: t.rev, hoja_sha256: t.hoja_marcada_sha256},
        'Anotar la presentación hecha a mano') : null,
      el('p', {clase: 'suave'}, 'Hoja de trabajo: sha256 ' + t.hoja_sha256 + ' ',
        el('button', {type: 'button', al_pulsar: function () {
          descargar('/api/v2/btw/' + encodeURIComponent(t.etiqueta) + '/hoja.csv',
                    'btw-' + t.etiqueta + '.csv');
        }}, 'Descargar la hoja')));
  }

  // ---------------------------------------------------------------- caja (§7)

  // El flujo de caja con un periodo pedido (§7 "custom period"): lo esperado que vence en el y
  // lo movido por el banco entre las dos fechas.
  function pintarCaja(contenedor, c) {
    vaciar(contenedor);
    var resultado = el('div');
    var form = el('form', {clase: 'linea', al_enviar: function (ev) {
      ev.preventDefault();
      abrirCaja(entradas.desde.value, entradas.hasta.value);
    }});
    var entradas = {desde: el('input', {type: 'date', name: 'desde'}),
                    hasta: el('input', {type: 'date', name: 'hasta'})};
    anadir(form, el('label', {}, 'desde ', entradas.desde), el('label', {}, 'hasta ',
      entradas.hasta), el('button', {type: 'submit'}, 'Ver el periodo'));
    anadir(contenedor, el('h2', {}, 'Caja'), form, resultado);
    if (c) { pintarFlujo(resultado, c); }
  }

  function pintarFlujo(contenedor, c) {
    vaciar(contenedor);
    var e = c.esperado;
    var ventanas = ['vencido', 'semana', 'mes', 'proximos_30', 'periodo', 'sin_fecha', 'total'];
    anadir(contenedor, el('p', {}, 'A ' + c.hoy + (c.ventanas.periodo ? ' · periodo del ' +
      c.ventanas.periodo[0] + ' al ' + c.ventanas.periodo[1] : '')),
      filas(['', 'Entra', 'Sale', 'Neto'], ventanas.filter(function (v) {
        return e.entrada[v] !== null && e.entrada[v] !== undefined; }).map(function (v) {
          return [NOMBRE_VENTANA[v] || v, importe(e.entrada[v]), importe(e.salida[v]),
            importe(e.neto[v])]; })),
      c.real ? el('p', {clase: 'suave'}, 'Movido por el banco en el periodo: cobrado ' +
        importe(c.real.cobrado.periodo) + ', pagado ' + importe(c.real.pagado.periodo)) : null,
      el('p', {clase: 'suave'}, c.estimado.importe_cent === null ? c.estimado.nota :
        'Estimado del planning (aparte): neto ' + importe(c.estimado.importe_cent) + '. ' +
        c.estimado.nota));
  }

  function abrirCaja(desde, hasta) {
    var partes = [];
    if (desde) { partes.push('desde=' + encodeURIComponent(desde)); }
    if (hasta) { partes.push('hasta=' + encodeURIComponent(hasta)); }
    return api('GET', '/api/v2/flujo' + (partes.length ? '?' + partes.join('&') : '')).then(
      function (r) { pintarCaja(document.getElementById('caja'), r.flujo_caja); }
    ).catch(function (error) { decir('No se puede ver la caja: ' + error.message, true); });
  }

  // Los importes de las cifras del BTW llegan en centimos: se escriben con coma decimal.
  function importe(cent) {
    if (cent === null || cent === undefined) { return ''; }
    var signo = cent < 0 ? '-' : '';
    var abs = Math.abs(cent);
    var euros = String(Math.floor(abs / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    var resto = String(abs % 100);
    return signo + euros + ',' + (resto.length < 2 ? '0' + resto : resto);
  }

  // ---------------------------------------------------------------- paso 12: historia (§12)

  function pintarHistorial(contenedor, h) {
    vaciar(contenedor);
    var d = h.documento;
    anadir(contenedor,
      d ? el('p', {}, 'Original: ' + d.nombre + ' · sha256 ' + d.sha256 + ' · ' +
        (d.conservado ? 'guardado en el almacén' : 'NO está en el almacén (Q4)') +
        ' · llegó por la vía ' + d.via) : el('p', {clase: 'suave'}, 'Sin documento: llegó ' +
        'de otro sistema.'),
      h.extracciones.length ? filas(['Extracción', 'Modelo', 'Prompt', 'Esquema', 'Cuándo',
        ''], h.extracciones.map(function (e) {
          return [e.id, e.modelo, e.prompt, e.esquema, e.extraido_en, e.vigente ? 'vigente' : '']; }))
        : null,
      h.relaciones.length ? el('h3', {}, 'Relaciones') : null,
      h.relaciones.length ? el('ul', {}, h.relaciones.map(function (r) {
        var otra = el('span', {clase: 'enlace', al_pulsar: function () { abrirFicha(r.otra_id); }},
          r.otra_numero || ('factura ' + r.otra_id));
        var cola = ' · ' + r.estado + (r.importe ? ' · ' + r.importe : '') +
          (r.retirada ? ' (retirada)' : '');
        return r.papel === 'origen' ? el('li', {}, 'Esta factura ' + r.tipo + ' ', otra, cola)
          : el('li', {}, otra, ' ' + r.tipo + ' esta factura', cola);
      })) : null,
      el('h3', {}, 'Cambios'),
      h.eventos.map(function (e) {
        var cambios = e.persona ? e.cambios : [];
        return el('div', {clase: 'evento' + (e.persona ? ' persona' : '')},
          el('div', {}, e.en + ' · ' + e.tipo + ' · ' + (e.usuario || e.actor || '') +
            (e.motivo ? ': «' + e.motivo + '»' : '') +
            (!e.persona && e.cambios.length ? ' (' + e.cambios.length + ' valores automáticos)' : '')),
          cambios.length ? filas(['Campo', 'Antes', 'Ahora', 'Fuente', 'Motivo'],
            cambios.map(function (c) {
              return [c.tabla + '.' + c.campo, c.anterior_texto, c.nuevo_texto,
                c.fuente_texto || c.fuente_nueva, c.motivo]; })) : null);
      }),
      el('h3', {}, 'Revisiones'),
      h.revisiones.length ? el('ul', {}, h.revisiones.map(function (r) {
        return el('li', {}, r.resultado + ' por ' + r.usuario + ' el ' + r.en +
          (r.vigente ? '' : ' — ya no vale') + (r.nota ? ': ' + r.nota : ''));
      })) : el('p', {clase: 'suave'}, 'Nunca se ha revisado.'),
      el('h3', {}, 'Avisos y su resolución'),
      h.hallazgos.map(function (x) {
        return el('div', {clase: 'evento'},
          el('div', {}, x.regla + ' ' + x.titulo + ' — ' + x.estado),
          el('div', {clase: 'suave'}, x.eventos.map(function (e) {
            return e.en + ' ' + e.tipo + (e.usuario ? ' (' + e.usuario + ')' : '') +
              (e.nota ? ': ' + e.nota : ''); }).join(' · ')),
          x.anulaciones.map(function (a) {
            return el('div', {clase: 'suave'}, 'Anulado por ' + a.usuario + ' el ' + a.en +
              (a.vigente_hasta ? ' hasta ' + a.vigente_hasta : '') + ': «' + a.motivo + '»' +
              (a.segunda_firma ? ', segunda firma de ' + a.segunda_firma : '') +
              (a.autoaprobada ? ' (autoaprobada)' : ''));
          }));
      }),
      h.excepciones.length ? el('div', {}, el('h3', {}, 'Excepciones'),
        filas(['Asunto', 'Estado', 'Resolución', 'Notas'], h.excepciones.map(function (e) {
          return [e.titulo, e.estado, e.resolucion, e.resolucion_notas]; }))) : null);
  }

  function abrirTrimestre(etiqueta) {
    estado.ficha = null;
    return api('GET', '/api/v2/btw/' + encodeURIComponent(etiqueta)).then(function (r) {
      pintarTrimestre(document.getElementById('ficha'), r.trimestre);
    }).catch(function (error) { decir(error.message, true); });
  }

  var SECCIONES = [['panel', 'Panel'], ['buscar', 'Buscar'], ['lista', 'Facturas'],
    ['partes', 'Proveedores y clientes'], ['objetos', 'Objetos'],
    ['ordenes', 'Órdenes de compra'], ['btw', 'BTW'], ['caja', 'Caja'], ['ficha', 'Ficha']];

  function pintarNavegacion(contenedor) {
    vaciar(contenedor);
    SECCIONES.forEach(function (s) {
      anadir(contenedor, el('button', {type: 'button', al_pulsar: function () {
        var destino = document.getElementById(s[0]);
        if (destino && destino.scrollIntoView) { destino.scrollIntoView(); }
      }}, s[1]));
    });
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
    api('GET', '/api/v2/panel').then(function (r) {
      pintarPanel(document.getElementById('panel'), r.panel);
    }).catch(function (error) { decir(error.message, true); });
    var lista = api('GET', '/api/v2/facturas').then(function (r) {
      pintarListado(document.getElementById('lista'), r.facturas);
    });
    Promise.all([api('GET', '/api/v2/proveedores'), api('GET', '/api/v2/clientes')]).then(
      function (r) {
        estado.proveedores = r[0].proveedores;
        estado.clientes = r[1].clientes;
        pintarPartes(document.getElementById('partes'), r[0].proveedores, r[1].clientes);
      });
    api('GET', '/api/v2/ordenes').then(function (r) {
      estado.ordenes = r.ordenes;
      pintarOrdenes(document.getElementById('ordenes'), r.ordenes);
    });
    api('GET', '/api/v2/objetos').then(function (r) {
      pintarObjetos(document.getElementById('objetos'), r);
    });
    api('GET', '/api/v2/btw').then(function (r) {
      pintarBtw(document.getElementById('btw'), r.btw);
    });
    abrirCaja('', '');
    if (estado.ficha !== null) { return lista.then(function () { return abrirFicha(estado.ficha); }); }
    return lista;
  }

  function abrirFicha(id) {
    estado.ficha = id;
    var ruta = '/api/v2/facturas/' + encodeURIComponent(String(id));
    return api('GET', ruta).then(function (r) {
      pintarDetalle(document.getElementById('ficha'), r.factura);
      return api('GET', ruta + '/historial');
    }).then(function (r) {
      var sitio = document.getElementById('historia-' + id);
      if (sitio) { pintarHistorial(sitio, r.historial); }
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
      return Promise.all([api('GET', '/api/v2/personas'), api('GET', '/api/v2/objetos'),
                          api('GET', '/api/v2/contrato'), api('GET', '/api/v2/recursos')]);
    }).then(function (r) {
      estado.personas = r[0].personas;
      estado.objetos = r[1].objetos;
      estado.recursos = r[3].recursos;
      pintarNavegacion(document.getElementById('navegacion'));
      return recargar().then(function () {
        pintarBuscador(document.getElementById('buscar'), r[2].filtros);
      });
    }).catch(function (error) { decir(error.message, true); });
  }

  function iniciar() {
    document.getElementById('entrar').addEventListener('submit', entrar);
  }

  window.BMSConsola = {el: el, pintarListado: pintarListado, pintarDetalle: pintarDetalle,
                       pintarPartes: pintarPartes, pintarParte: pintarParte,
                       pintarOrdenes: pintarOrdenes, pintarOrden: pintarOrden,
                       pintarObjeto: pintarObjeto, pintarPanel: pintarPanel,
                       pintarBuscador: pintarBuscador, pintarBusqueda: pintarBusqueda,
                       pintarObjetos: pintarObjetos, pintarBtw: pintarBtw,
                       pintarTrimestre: pintarTrimestre, pintarHistorial: pintarHistorial,
                       pintarNavegacion: pintarNavegacion, importe: importe,
                       pintarCaja: pintarCaja, pintarFlujo: pintarFlujo,
                       resumen: resumen, estado: estado};
  document.addEventListener('DOMContentLoaded', iniciar);
})();
"""
