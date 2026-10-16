# La imagen del entorno local (paso 13, docs/entorno-local.md). Una sola imagen para
# los cuatro papeles de docker-compose.yml: la consola, el lector de PDF, la salida
# (el proxy hacia la API de Anthropic) y las ordenes sueltas (importar, copias, la
# base de prueba). Lo que cambia entre ellos es la orden y la red, no el codigo.
#
# Lo que se fija aqui y por que:
# - la base va fijada por etiqueta y por digest: la misma imagen hoy y dentro de un
#   ano, y nadie la cambia por debajo en Docker Hub;
# - las dependencias, con su version y su sha256 (requirements.txt, --require-hashes);
# - corre como un usuario sin privilegios (uid 10001), nunca como root;
# - el sistema de ficheros de la imagen es de solo lectura en compose (read_only): lo
#   unico que se escribe es /datos (el volumen) y /tmp (en memoria);
# - la clave de la API no entra nunca en la imagen: es un secreto de Docker que solo
#   ve el lector, en tiempo de ejecucion.
FROM python:3.11.17-slim-trixie@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    TZ=Europe/Amsterdam

WORKDIR /app

COPY docker/requirements.txt /app/docker/requirements.txt
# ca_extra es opcional: solo hace falta detras de un proxy de empresa que intercepta
# TLS (docker build --secret id=ca_extra,src=su-certificado.pem). No queda en la imagen.
RUN --mount=type=secret,id=ca_extra,required=false \
    if [ -s /run/secrets/ca_extra ]; then export PIP_CERT=/run/secrets/ca_extra; fi; \
    pip install --no-cache-dir --only-binary=:all: --require-hashes \
        -r /app/docker/requirements.txt

COPY pyproject.toml README.md /app/
COPY config /app/config
COPY src /app/src

RUN python -m compileall -q /app/src \
    && groupadd --gid 10001 bms \
    && useradd --uid 10001 --gid bms --no-create-home --home-dir /tmp \
        --shell /usr/sbin/nologin bms \
    && mkdir -p /datos /buzon \
    && chown bms:bms /datos

USER 10001:10001

EXPOSE 8765

# La de la consola. La salida y el lector llevan la suya en docker-compose.yml.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "bms_agent.cli", "salud", "127.0.0.1:8765"]

ENTRYPOINT ["python", "-m", "bms_agent.cli"]
CMD ["serve", "--contenedor", "--puerto", "8765", "--out", "/datos/out"]
