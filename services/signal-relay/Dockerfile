FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 10001 relay \
    && useradd --uid 10001 --gid relay --create-home --shell /usr/sbin/nologin relay \
    && mkdir /data /reticulum \
    && chown relay:relay /data /reticulum

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

USER relay

EXPOSE 8787

CMD ["uvicorn", "signal_relay.app:app", "--host", "0.0.0.0", "--port", "8787"]