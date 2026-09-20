FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONN_PILOT_CATALOG=/app/catalog

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY catalog ./catalog
COPY knowledge ./knowledge
RUN pip install --no-cache-dir .

CMD ["python", "-m", "conn_pilot.control_plane"]
