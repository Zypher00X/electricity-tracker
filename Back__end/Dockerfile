FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

WORKDIR /app
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./

RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
    && python -m pip uninstall -y pip \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app

COPY --chown=10001:10001 app ./app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import os,urllib.request,urllib.parse; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/health', headers={'Host':urllib.parse.urlsplit(os.getenv('PUBLIC_ORIGIN','http://localhost')).netloc}), timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
