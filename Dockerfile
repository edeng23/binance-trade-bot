FROM python:3.8 as base

FROM base as builder

RUN mkdir /install

WORKDIR /install

COPY requirements.txt /requirements.txt

RUN pip install --prefix=/install -r /requirements.txt

FROM base

WORKDIR /app

COPY --from=builder /install /usr/local\
COPY . /app

RUN chmod +x entrypoint.sh


ENTRYPOINT [ "entrypoint.sh" ]
CMD ["python", "crypto_trading.py"]
