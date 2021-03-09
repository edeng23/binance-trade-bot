FROM --platform=$BUILDPLATFORM python:3.8 as builder

WORKDIR /install

COPY requirements.txt /requirements.txt
COPY . .
COPY .git .git

RUN apt-get update && apt-get install -y curl && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    . /root/.cargo/env && \
    rustup toolchain install 1.41.0 && \
    pip install setuptools_cythonize setuptools_scm && \
    pip install --prefix=/install -r /requirements.txt && \
    python setup.py install --prefix=/install --cythonize

FROM python:3.8-slim

WORKDIR /app

COPY --from=builder /install /usr/local

CMD ["binance-trade-bot"]
