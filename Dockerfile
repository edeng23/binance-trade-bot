FROM --platform=$BUILDPLATFORM python:3.8 as builder

WORKDIR /install

COPY requirements.txt /requirements.txt

RUN apt-get update && apt-get install -y rustc && \
    pip install --prefix=/install -r /requirements.txt

FROM python:3.8-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

CMD ["python", "-m", "binance_trade_bot"]
