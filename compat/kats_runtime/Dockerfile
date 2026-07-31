FROM python:3.10-slim-bullseye

ENV HOME=/tmp \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp/.cache

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir \
        "setuptools<81" \
        wheel \
        "cython==0.29.37" \
        "numpy==1.21.6" \
    && pip install --no-cache-dir --no-build-isolation --no-deps -r requirements.lock

RUN git clone --filter=blob:none https://github.com/facebookresearch/Kats.git /tmp/kats \
    && git -C /tmp/kats checkout 4145be4e5c962a06f15e833830f134d7758a7467 \
    && MINIMAL_KATS=1 pip install --no-cache-dir --no-deps /tmp/kats \
    && rm -rf /tmp/kats

COPY app.py engine.py ./

RUN addgroup --system kats \
    && adduser --system --ingroup kats --home /nonexistent kats

USER kats
EXPOSE 8096

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8096", "--no-access-log"]
