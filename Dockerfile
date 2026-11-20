# ---- build stage: install dependencies into a virtualenv
FROM python:3.12-slim AS build
WORKDIR /build
RUN python -m venv /venv
COPY requirements.txt .
RUN /venv/bin/pip install --no-cache-dir -r requirements.txt

# ---- runtime stage: no compiler, no pip cache, non-root user
FROM python:3.12-slim
ARG APP_VERSION=dev
ENV PATH="/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=$APP_VERSION
RUN useradd --uid 10001 --no-create-home app
COPY --from=build /venv /venv
WORKDIR /srv
COPY app ./app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=2s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz').status!=200)"
# uvicorn reads WEB_CONCURRENCY as the worker count
ENV WEB_CONCURRENCY=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
