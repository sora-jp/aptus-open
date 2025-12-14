FROM alpine:latest
LABEL org.opencontainers.image.authors="Oskar Tornevall <oskar.tornevall@gmail.com>"

WORKDIR /app

COPY pyproject.toml poetry.lock ./
COPY ./aptus_open ./aptus_open

RUN apk add --no-cache python3 py3-pip && pip3 install . --break-system-packages
CMD ["aptus_open", "-s", "/etc/secrets.toml"]
