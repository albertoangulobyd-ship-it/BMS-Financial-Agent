"""GraphFalso: Microsoft de mentira para las pruebas del correo (paso 18, diseno §7.1).

No es un test: es el doble de login.microsoftonline.com y graph.microsoft.com que el cliente
recibe por inyeccion (`ClienteGraph(..., transporte=falso.transporte)`, un httpx2.MockTransport).
Contesta lo que contestaria Microsoft, con sus formas (tests/fixtures/correo/*.json y los
enlaces de docs-ms concepts_delta-query-messages.md):

- el token: comprueba de verdad la asercion con la parte publica del certificado de prueba
  (PS256, x5t#S256, aud del inquilino, iss = sub = la aplicacion, exp - nbf <= 10 min, jti
  nuevo, en su plazo) y da un JWT sin firmar con tid, appid, aud y, si se le dice, roles;
- la delta de la bandeja y de "no deseado", por paginas (Prefer: odata.maxpagesize), con los
  enlaces en una de las formas de Microsoft: `clave` (users('x%40y')/mailfolders('AQMk...'),
  en minusculas), `guid` (users/<guid>/mailFolders/AAMk...) o `primera` (la ruta de la primera
  peticion);
- la lista de adjuntos (por paginas, si se le dice: `max_pagina_adjuntos`, con el nextLink en la
  forma de clave `users('x%40y')/messages('AAMk...')/attachments`), el contenido de uno
  ($value), el buzon, el de control y /users;
- los fallos que se le pidan (`fallar`).

Y apunta cada peticion (metodo, host, ruta, consulta, cabeceras sin Authorization). Lo que
Microsoft no deberia ver nunca de este cliente queda en `violaciones` (y el test falla al
final, con `comprobar()`): un metodo que no es GET (salvo el POST del token), un $expand, un
$select con el cuerpo, una peticion sin Prefer IdType="ImmutableId", el $value de un adjunto
que no es de fichero, otro host u otro buzon.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import httpx2
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "correo"
LOGIN = "login.microsoftonline.com"
GRAPH = "graph.microsoft.com"
CARPETAS = {"inbox": "AQMkADAwATM0MDAAMS1iNTcwLWI2NTEtMDACLTAwCgAuAAADRJ0iIAAAAQEAAAA=",
            "junkemail": "AQMkADAwATM0MDAAMS1iNTcwLWI2NTEtMDACLTAwCgAuAAADRJ0iIAAAAQ8AAAA="}
GUID_BUZON = "0f1e2d3c-4b5a-4968-8776-655443322110"
CUERPO = ("body", "bodypreview", "uniquebody")
TROZO = 64 * 1024


def fixture(nombre: str) -> Any:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


def mensajes() -> dict[str, dict]:
    return {k: v for k, v in fixture("mensajes.json").items() if not k.startswith("_")}


def adjuntos() -> dict[str, list[dict]]:
    return {k: v for k, v in fixture("adjuntos.json").items() if not k.startswith("_")}


def pdf(texto: str, tamano: int = 0) -> bytes:
    """Un PDF de prueba (solo la cabecera importa: nadie lo analiza), de `tamano` bytes."""
    datos = f"%PDF-1.7\n% {texto}\n".encode()
    return datos + b"0" * max(0, tamano - len(datos))


def _b64d(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


@dataclass
class Peticion:
    metodo: str
    host: str
    ruta: str
    consulta: str
    cabeceras: dict[str, str]
    tipo: str = ""

    @property
    def parametros(self) -> dict[str, list[str]]:
        return parse_qs(self.consulta, keep_blank_values=True)


@dataclass
class Fallo:
    tipo: str
    estado: int
    cuerpo: Any = None
    cabeceras: dict[str, str] = field(default_factory=dict)
    veces: int = 1
    cuando: Callable[[Peticion], bool] | None = None
    excepcion: BaseException | None = None


@dataclass
class _Enlace:
    carpeta: str
    posicion: int
    final: int | None       # en una pagina de la primera pasada, hasta donde llega
    filtro: datetime | None


class GraphFalso:
    def __init__(self, *, certificado: bytes, inquilino: str, aplicacion: str, buzon: str,
                 control: str, ahora: Callable[[], datetime], roles: list[str] | None = None,
                 forma: str = "clave") -> None:
        self.publico = x509.load_pem_x509_certificate(certificado)
        self.x5t = _b64(hashlib.sha256(self.publico.public_bytes(
            serialization.Encoding.DER)).digest())
        self.inquilino, self.aplicacion = inquilino, aplicacion
        self.buzon, self.control = buzon, control
        self.ahora = ahora
        self.roles = roles
        self.forma = forma
        self.tid: str | None = None          # otro inquilino en el token, si se pide
        # Lo que cambia en la carga del token (None quita ese campo): otra aud, otra appid...
        self.en_el_token: dict[str, Any] = {}
        self.estado_buzon = 200
        self.estado_control = 403
        self.estado_usuarios = 403
        self.carpetas: dict[str, list[dict]] = {"inbox": [], "junkemail": []}
        self.listas: dict[str, list[dict]] = {}
        self.contenidos: dict[tuple[str, str], bytes | Callable[[], Iterator[bytes]]] = {}
        self.extra_en_mensajes: dict[str, Any] = {}
        self.contenido_en_la_lista = False
        self.siguiente_malo: str | None = None
        self.max_pagina: int | None = None
        self.max_pagina_adjuntos: int | None = None
        self.siguiente_adjuntos_malo: str | None = None
        self.servido_json = self.total_json = 0
        self.fallos: list[Fallo] = []
        self.peticiones: list[Peticion] = []
        self.violaciones: list[str] = []
        self.tokens: set[str] = set()
        self.asercion_vista = ""
        self.jti: set[str] = set()
        self.servidos: dict[str, int] = {}
        self._enlaces: dict[str, _Enlace] = {}
        self._enlaces_adjuntos: dict[str, tuple[str, int]] = {}
        self.transporte = httpx2.MockTransport(self._responder)

    # ---------------------------------------------------------------- preparar

    def llega(self, mensaje: dict, carpeta: str = "inbox", adjuntos: list[dict] | None = None,
              contenidos: dict[str, bytes | Callable[[], Iterator[bytes]]] | None = None
              ) -> None:
        """Un mensaje nuevo en una carpeta, con su lista de adjuntos y lo que bajan."""
        self.carpetas[carpeta].append(dict(mensaje))
        if "id" in mensaje and adjuntos is not None:
            self.listas[mensaje["id"]] = [dict(a) for a in adjuntos]
        for aid, contenido in (contenidos or {}).items():
            self.contenidos[(mensaje["id"], aid)] = contenido

    def fallar(self, tipo: str, estado: int = 500, cuerpo: Any = None, *, veces: int = 1,
               cabeceras: dict[str, str] | None = None,
               cuando: Callable[[Peticion], bool] | None = None,
               excepcion: BaseException | None = None) -> None:
        """Las proximas `veces` peticiones de ese tipo (token, delta, adjuntos, valor, buzon,
        control, usuarios) contestan esto (o lanzan `excepcion`, como un corte de red)."""
        self.fallos.append(Fallo(tipo, estado, cuerpo, cabeceras or {}, veces, cuando,
                                 excepcion))

    def comprobar(self) -> None:
        assert self.violaciones == [], self.violaciones

    def de_tipo(self, tipo: str) -> list[Peticion]:
        return [p for p in self.peticiones if p.tipo == tipo]

    # ---------------------------------------------------------------- contestar

    def _responder(self, request: httpx2.Request) -> httpx2.Response:
        url = request.url
        ruta = url.raw_path.decode("ascii").split("?", 1)[0]
        consulta = url.query.decode("ascii")
        cabeceras = {k.lower(): v for k, v in request.headers.items()
                     if k.lower() != "authorization"}
        peticion = Peticion(request.method, url.host, ruta, consulta, cabeceras)
        self.peticiones.append(peticion)
        if url.host == LOGIN:
            peticion.tipo = "token"
            return self._con_fallo(peticion, lambda: self._token(request, ruta))
        if url.host != GRAPH or url.scheme != "https" or url.port not in (None, 443):
            self.violaciones.append(f"peticion a otro sitio: {url.scheme}://{url.host}:{url.port}")
            return httpx2.Response(404)
        if request.method != "GET":
            self.violaciones.append(f"{request.method} a Graph")
            return httpx2.Response(405)
        crudo = unquote(consulta).lower()
        if "$expand" in crudo or "expand=" in crudo:
            self.violaciones.append(f"$expand: {ruta}")
        for nombre in ("$select",):
            for valor in peticion.parametros.get(nombre, []):
                if any(c in valor.lower().split(",") for c in CUERPO):
                    self.violaciones.append(f"el cuerpo en $select: {valor}")
        if 'idtype="immutableid"' not in cabeceras.get("prefer", "").lower():
            self.violaciones.append(f"sin Prefer IdType=ImmutableId: {ruta}")
        autorizacion = request.headers.get("authorization", "")
        if not autorizacion.startswith("Bearer ") or autorizacion[7:] not in self.tokens:
            return self._json(401, fixture("error-token-graph.json"))
        return self._graph(peticion)

    def _con_fallo(self, peticion: Peticion, normal: Callable[[], httpx2.Response]
                   ) -> httpx2.Response:
        for fallo in self.fallos:
            if fallo.veces > 0 and fallo.tipo == peticion.tipo and (
                    fallo.cuando is None or fallo.cuando(peticion)):
                fallo.veces -= 1
                if fallo.excepcion is not None:
                    raise fallo.excepcion
                return self._json(fallo.estado, fallo.cuerpo, fallo.cabeceras)
        return normal()

    def _json(self, estado: int, cuerpo: Any, cabeceras: dict[str, str] | None = None,
              trozos: bool = False) -> httpx2.Response:
        """Una respuesta JSON; con `trozos`, sin Content-Length y por trozos de 64 KiB, contando
        en `servido_json` cuanto se ha leido de verdad."""
        datos = b"" if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
        cabeceras = {"Content-Type": "application/json", **(cabeceras or {})}
        if trozos:
            self.servido_json = 0
            self.total_json = len(datos)

            def contado() -> Iterator[bytes]:
                for i in range(0, len(datos), TROZO):
                    self.servido_json += len(datos[i:i + TROZO])
                    yield datos[i:i + TROZO]

            return httpx2.Response(estado, headers=cabeceras, content=contado())
        return httpx2.Response(estado, headers=cabeceras, content=datos)

    # ---------------------------------------------------------------- el token

    def _token(self, request: httpx2.Request, ruta: str) -> httpx2.Response:
        malo = self._json(401, fixture("token-invalid_client.json"))
        if request.method != "POST" or ruta != f"/{self.inquilino}/oauth2/v2.0/token":
            self.violaciones.append(f"token: {request.method} {ruta}")
            return malo
        if not request.headers.get("content-type", "").startswith(
                "application/x-www-form-urlencoded"):
            self.violaciones.append("token: el cuerpo no es un formulario")
            return malo
        formulario = {k: v[0] for k, v in parse_qs(request.read().decode("ascii")).items()}
        esperado = {"client_id": self.aplicacion, "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                    "client_assertion_type":
                        "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"}
        if {k: formulario.get(k) for k in esperado} != esperado or set(formulario) != {
                *esperado, "client_assertion"}:
            self.violaciones.append("token: el formulario no es el de client credentials")
            return malo
        self.asercion_vista = formulario["client_assertion"]
        if not self._asercion_valida(formulario["client_assertion"]):
            return malo
        momento = int(self.ahora().timestamp())
        carga = {"aud": "https://graph.microsoft.com",
                 "iss": f"https://sts.windows.net/{self.tid or self.inquilino}/",
                 "iat": momento, "nbf": momento, "exp": momento + 3599,
                 "appid": self.aplicacion, "appidacr": "2", "idtyp": "app",
                 "tid": self.tid or self.inquilino, "ver": "1.0",
                 "oid": "11111111-0000-4000-8000-000000000001"}
        if self.roles is not None:
            carga["roles"] = self.roles
        for nombre, valor in self.en_el_token.items():
            if valor is None:
                carga.pop(nombre, None)
            else:
                carga[nombre] = valor
        token = ".".join([_b64(b'{"typ":"JWT","alg":"none"}'),
                          _b64(json.dumps(carga).encode()), ""])
        token = token + _b64(secrets.token_bytes(16))   # que cada uno sea otro
        self.tokens.add(token)
        respuesta = fixture("token.json")
        respuesta["access_token"] = token
        return self._json(200, respuesta)

    def _asercion_valida(self, asercion: str) -> bool:
        """La asercion como la comprueba Entra: la firma con la parte publica y sus campos."""
        try:
            cabecera, carga, firma = asercion.split(".")
            datos_cabecera = json.loads(_b64d(cabecera))
            datos = json.loads(_b64d(carga))
            self.publico.public_key().verify(
                _b64d(firma), f"{cabecera}.{carga}".encode("ascii"),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
        except (ValueError, InvalidSignature):
            self.violaciones.append("token: la asercion no es un JWT firmado por el certificado")
            return False
        ahora = int(self.ahora().timestamp())
        try:
            plazo = datos["exp"] - datos["nbf"]
            en_plazo = datos["nbf"] - 300 <= ahora < datos["exp"]
        except (KeyError, TypeError):
            plazo, en_plazo = 0, False
        bien = (datos_cabecera == {"alg": "PS256", "typ": "JWT", "x5t#S256": self.x5t}
                and datos.get("aud") == (f"https://login.microsoftonline.com/{self.inquilino}"
                                         "/oauth2/v2.0/token")
                and datos.get("iss") == datos.get("sub") == self.aplicacion
                and isinstance(datos.get("jti"), str) and datos["jti"] not in self.jti
                and 0 < plazo <= 600 and en_plazo)
        if not bien:
            self.violaciones.append(f"token: la asercion no es la que pide Entra: {datos}")
            return False
        self.jti.add(datos["jti"])
        return True

    # ---------------------------------------------------------------- Graph

    def _usuario(self, segmento: str) -> str | None:
        """El buzon de un tramo de la ruta: users/<direccion>, users('<direccion>') o el GUID."""
        texto = unquote(segmento)
        if texto.startswith("('") and texto.endswith("')"):
            texto = texto[2:-2]
        if texto.lower() == GUID_BUZON:
            return self.buzon
        return texto.lower()

    def _graph(self, peticion: Peticion) -> httpx2.Response:
        ruta = peticion.ruta
        if ruta == "/v1.0/users":
            peticion.tipo = "usuarios"
            return self._con_fallo(peticion, lambda: self._estado(self.estado_usuarios))
        bajo = ruta.lower()
        if not bajo.startswith("/v1.0/users"):
            self.violaciones.append(f"ruta de Graph inesperada: {ruta}")
            return httpx2.Response(404)
        resto = ruta[len("/v1.0/users"):]
        if resto.startswith("/"):
            usuario, _sep, cola = resto[1:].partition("/")
        else:
            usuario, _sep, cola = resto.partition("/")
        buzon = self._usuario(usuario)
        cola_baja = cola.lower()
        if cola_baja.endswith("messages/delta"):
            peticion.tipo = "delta"
            if buzon != self.buzon:
                self.violaciones.append("delta de otro buzon")
            return self._con_fallo(peticion, lambda: self._delta(peticion, cola))
        if cola_baja == "mailfolders/inbox":
            peticion.tipo = "buzon" if buzon == self.buzon else (
                "control" if buzon == self.control else "otro")
            if peticion.tipo == "otro":
                self.violaciones.append("otro buzon")
            estado = self.estado_buzon if peticion.tipo == "buzon" else self.estado_control
            return self._con_fallo(peticion, lambda: self._estado(estado, CARPETAS["inbox"]))
        if buzon != self.buzon:
            self.violaciones.append("otro buzon")
            return self._json(403, fixture("error-acceso.json"))
        trozos = cola.split("/")
        if len(trozos) == 3 and trozos[0] == "messages" and trozos[2] == "attachments":
            peticion.tipo = "adjuntos"
            return self._con_fallo(peticion, lambda: self._lista(unquote(trozos[1]), peticion))
        if (len(trozos) == 2 and trozos[0].startswith("messages('") and trozos[0].endswith("')")
                and trozos[1] == "attachments"):
            # La forma de clave de un nextLink de la lista: messages('AAMk...')/attachments.
            peticion.tipo = "adjuntos"
            return self._con_fallo(peticion, lambda: self._lista(
                unquote(trozos[0][len("messages('"):-2]), peticion))
        if (len(trozos) == 5 and trozos[0] == "messages" and trozos[2] == "attachments"
                and trozos[4] == "$value"):
            peticion.tipo = "valor"
            return self._con_fallo(peticion, lambda: self._valor(unquote(trozos[1]),
                                                                 unquote(trozos[3])))
        self.violaciones.append(f"ruta de Graph inesperada: {ruta}")
        return httpx2.Response(404)

    def _estado(self, estado: int, carpeta: str | None = None) -> httpx2.Response:
        if estado == 200:
            return self._json(200, {"@odata.context": "https://graph.microsoft.com/v1.0/"
                                    "$metadata#users('x')/mailFolders(id)/$entity",
                                    "id": carpeta or "x"} if carpeta else {
                                        "value": [{"id": GUID_BUZON}]})
        if estado == 404:
            return self._json(404, fixture("error-no-existe.json"))
        return self._json(estado, fixture("error-acceso.json"))

    def _enlace(self, carpeta: str, enlace: _Enlace, delta: bool) -> str:
        token = _b64(secrets.token_bytes(18))
        self._enlaces[token] = enlace
        parametro = "$deltatoken" if delta else "$skiptoken"
        if self.forma == "clave":
            base = (f"https://graph.microsoft.com/v1.0/users('{quote(self.buzon, safe='')}')"
                    f"/mailfolders('{CARPETAS[carpeta]}')/messages/delta")
        elif self.forma == "guid":
            base = (f"https://graph.microsoft.com/v1.0/users/{GUID_BUZON}/mailFolders/"
                    f"{CARPETAS[carpeta]}/messages/delta")
        else:
            base = (f"https://graph.microsoft.com/v1.0/users/{self.buzon}/mailFolders/"
                    f"{carpeta}/messages/delta")
        return f"{base}?{parametro}={token}"

    def _delta(self, peticion: Peticion, cola: str) -> httpx2.Response:
        parametros = peticion.parametros
        token = (parametros.get("$skiptoken") or parametros.get("$deltatoken") or [None])[0]
        tamano = 10
        for parte in peticion.cabeceras.get("prefer", "").split(","):
            nombre, _sep, valor = parte.strip().partition("=")
            if nombre == "odata.maxpagesize" and valor.isdigit():
                tamano = int(valor)
        if self.max_pagina is not None:
            tamano = min(tamano, self.max_pagina)
        if token is None:
            carpeta = cola.split("/")[1].lower() if cola.lower().startswith("mailfolders/") else ""
            if carpeta not in self.carpetas:
                self.violaciones.append(f"delta de una carpeta inesperada: {cola}")
                return httpx2.Response(404)
            if parametros.get("changeType") != ["created"]:
                self.violaciones.append("la primera delta sin changeType=created")
            filtro = (parametros.get("$filter") or [""])[0]
            if not filtro.startswith("receivedDateTime ge "):
                self.violaciones.append(f"la primera delta sin el filtro de fecha: {filtro}")
                return httpx2.Response(400)
            desde = datetime.fromisoformat(filtro.split(" ge ", 1)[1].replace("Z", "+00:00"))
            enlace = _Enlace(carpeta, 0, len(self.carpetas[carpeta]), desde)
        else:
            if token not in self._enlaces:
                return self._json(400, fixture("error-sin-estado.json"))
            enlace = self._enlaces[token]
            if enlace.final is None:   # un deltaLink: lo que ha llegado desde entonces
                enlace = _Enlace(enlace.carpeta, enlace.posicion,
                                 len(self.carpetas[enlace.carpeta]), None)
        lista = self.carpetas[enlace.carpeta]
        cuantos = 0
        valor = []
        posicion = enlace.posicion
        while posicion < enlace.final and cuantos < tamano:
            mensaje = lista[posicion]
            posicion += 1
            fecha = mensaje.get("receivedDateTime")
            try:
                antes = enlace.filtro is not None and datetime.fromisoformat(
                    str(fecha).replace("Z", "+00:00")) < enlace.filtro
            except ValueError:
                antes = False
            if antes:
                continue
            valor.append({**mensaje, **self.extra_en_mensajes})
            cuantos += 1
        cuerpo: dict[str, Any] = {"@odata.context": "https://graph.microsoft.com/v1.0/"
                                  "$metadata#Collection(message)", "value": valor}
        if posicion < enlace.final:
            siguiente = _Enlace(enlace.carpeta, posicion, enlace.final, enlace.filtro)
            cuerpo["@odata.nextLink"] = (
                self._enlace(enlace.carpeta, siguiente, False) if self.siguiente_malo is None
                else self.siguiente_malo)
        else:
            cuerpo["@odata.deltaLink"] = self._enlace(
                enlace.carpeta, _Enlace(enlace.carpeta, posicion, None, None), True)
        return self._json(200, cuerpo, trozos=True)

    def _lista(self, mensaje_id: str, peticion: Peticion) -> httpx2.Response:
        parametros = peticion.parametros
        if parametros.get("$select") != ["id,name,contentType,size,isInline"]:
            self.violaciones.append(f"lista de adjuntos sin el $select: {parametros}")
        if mensaje_id not in self.listas:
            return self._json(404, fixture("error-no-existe.json"))
        desde = 0
        token = (parametros.get("$skiptoken") or [None])[0]
        if token is not None:
            if self._enlaces_adjuntos.get(token, ("", 0))[0] != mensaje_id:
                self.violaciones.append("un nextLink de adjuntos que no dio el falso")
                return self._json(400, fixture("error-sin-estado.json"))
            desde = self._enlaces_adjuntos[token][1]
        todos = self.listas[mensaje_id]
        hasta = len(todos) if self.max_pagina_adjuntos is None else min(
            len(todos), desde + self.max_pagina_adjuntos)
        valor = []
        for adjunto in todos[desde:hasta]:
            fila = dict(adjunto)
            contenido = self.contenidos.get((mensaje_id, adjunto["id"]))
            if self.contenido_en_la_lista and isinstance(contenido, bytes):
                fila["contentBytes"] = base64.b64encode(contenido).decode("ascii")
            valor.append(fila)
        cuerpo: dict[str, Any] = {"@odata.context": "https://graph.microsoft.com/v1.0/"
                                  "$metadata#users('x')/messages('y')/attachments",
                                  "value": valor}
        if hasta < len(todos):
            siguiente = _b64(secrets.token_bytes(12))
            self._enlaces_adjuntos[siguiente] = (mensaje_id, hasta)
            cuerpo["@odata.nextLink"] = self.siguiente_adjuntos_malo or (
                f"https://graph.microsoft.com/v1.0/users('{quote(self.buzon, safe='')}')"
                f"/messages('{quote(mensaje_id, safe='=-_')}')/attachments"
                f"?$select=id,name,contentType,size,isInline&$skiptoken={siguiente}")
        return self._json(200, cuerpo, trozos=True)

    def _valor(self, mensaje_id: str, adjunto_id: str) -> httpx2.Response:
        adjunto = next((a for a in self.listas.get(mensaje_id, []) if a["id"] == adjunto_id),
                       None)
        if adjunto is None:
            return self._json(404, fixture("error-no-existe.json"))
        tipo = adjunto.get("@odata.type", "").lstrip("#").lower()
        if tipo != "microsoft.graph.fileattachment":
            self.violaciones.append(f"$value de un {tipo}")
            return httpx2.Response(405)
        contenido = self.contenidos.get((mensaje_id, adjunto_id))
        if contenido is None:
            return self._json(404, fixture("error-no-existe.json"))
        clave = f"{mensaje_id}/{adjunto_id}"
        self.servidos[clave] = 0
        if isinstance(contenido, bytes):
            trozos: Iterator[bytes] = iter([contenido[i:i + TROZO]
                                            for i in range(0, len(contenido), TROZO)])
        else:
            trozos = contenido()

        def contado() -> Iterator[bytes]:
            for trozo in trozos:
                self.servidos[clave] += len(trozo)
                yield trozo

        return httpx2.Response(200, headers={"Content-Type": adjunto.get("contentType")
                                             or "application/octet-stream"},
                               content=contado())


def crear_certificado(carpeta: Path, ahora: datetime) -> tuple[Path, Path]:
    """Un certificado de prueba (RSA 3072, tarda: una vez por modulo) que vale en `ahora`;
    devuelve su .pem y su .cer."""
    from bms_agent.correo import certificado

    carpeta.mkdir(parents=True, exist_ok=True)
    certificado.crear(carpeta, ahora=ahora - timedelta(days=1))
    return certificado.rutas(carpeta)
