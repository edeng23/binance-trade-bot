FROM python:3.8 as builder

WORKDIR /install

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir --prefix=/install -r /requirements.txt

FROM python:3.8-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

RUN chmod +x entrypoint.sh

ENTRYPOINT [ "entrypoint.sh" ]
CMD ["python", "crypto_trading.py"]
