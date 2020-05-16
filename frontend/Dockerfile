FROM java:openjdk-8-jre-alpine as builder
LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

RUN apk add --no-cache openssl && \
    wget https://dl.google.com/closure-compiler/compiler-latest.tar.gz && \
    tar -xzvf compiler-latest.tar.gz

COPY ./webapp/render/static/js/custom/ /root/
COPY ./minify-js.sh /root/
RUN mkdir /root/prod/ && ./minify-js.sh

FROM mavromat/alpine-python:3.6

WORKDIR /root

RUN apk update && apk add --no-cache openssl-dev libffi-dev py-openssl sqlite-dev sqlite

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade 'pip<19.0' && \
    pip --no-cache-dir install -r requirements.txt

RUN mkdir -p /etc/artemis/ && mkdir -p /var/log/artemis/

COPY ./webapp/configs/* /etc/artemis/

COPY entrypoint init.py wait-for ./
COPY webapp ./webapp
RUN rm /root/webapp/render/static/js/custom/*
COPY --from=builder /root/prod/ /root/webapp/render/static/js/custom/

ENTRYPOINT ["./entrypoint"]
