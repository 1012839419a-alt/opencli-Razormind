FROM python:3.13-slim-bookworm

ARG PAW_LLAMA_WHEEL_SHA256=bb121ab711305a6e2e44a4fce59740a3de489ae0f320d4240d890f8063bee70a
ARG PAW_SDK_WHEEL_SHA256=c1d8bc54bc4225ff882722cc4986e7b29912225bcd5ebe215297e5dcf8cfa68c

ENV HOME=/tmp \
    PAW_OFFLINE=1 \
    PAW_CACHE_DIR=/var/cache/paw \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The vendor wheel is deliberately used instead of a source distribution, so
# the sidecar never compiles llama.cpp. Its 0.3.19 wheel omits RECORD, which
# pip refuses to install; extract that signed wheel directly, then install the
RUN mkdir -p /tmp/paw-wheels \
    && pip download --no-deps --only-binary=:all: \
        --extra-index-url https://pypi.programasweights.com/simple/ \
        --dest /tmp/paw-wheels "llama-cpp-python==0.3.19" \
    && echo "${PAW_LLAMA_WHEEL_SHA256}  /tmp/paw-wheels/llama_cpp_python-0.3.19-cp313-cp313-linux_x86_64.whl" | sha256sum -c - \
    && python -m zipfile -e /tmp/paw-wheels/llama_cpp_python-0.3.19-cp313-cp313-linux_x86_64.whl /usr/local/lib/python3.13/site-packages \
    && pip install --no-cache-dir \
        "fastapi==0.141.1" \
        "diskcache==5.6.3" \
        "jinja2==3.1.6" \
        "httpx==0.28.1" \
        "numpy==2.5.2" \
        "uvicorn==0.52.4" \
    && pip download --no-deps --only-binary=:all: \
        --extra-index-url https://pypi.programasweights.com/simple/ \
        --dest /tmp/paw-wheels "programasweights==0.4.4" \
    && echo "${PAW_SDK_WHEEL_SHA256}  /tmp/paw-wheels/programasweights-0.4.4-py3-none-any.whl" | sha256sum -c - \
    && pip install --no-cache-dir --no-deps \
        /tmp/paw-wheels/programasweights-0.4.4-py3-none-any.whl \
    && rm -rf /tmp/paw-wheels

RUN addgroup --system paw \
    && adduser --system --ingroup paw --home /nonexistent paw

WORKDIR /app
COPY app.py engine.py ./

USER paw
EXPOSE 8097

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8097", "--no-access-log"]
