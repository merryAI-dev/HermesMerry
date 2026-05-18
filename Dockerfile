FROM python:3.12-slim@sha256:bf73779de6dbd030f3d189eeeb246286965832761ace318c1518300f76c0840d

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin hermes

COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock --no-cache-dir

COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs

RUN pip install --no-deps . --no-cache-dir

USER hermes

ENTRYPOINT ["python3", "-m", "merry_runtime.jobs"]
