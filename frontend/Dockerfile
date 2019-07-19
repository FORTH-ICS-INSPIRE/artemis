FROM java:openjdk-8-jre-alpine as builder
LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

RUN apk add --no-cache openssl && \
    wget https://dl.google.com/closure-compiler/compiler-latest.tar.gz && \
    tar -xzvf compiler-latest.tar.gz

COPY ./webapp/render/static/js/custom/ /root/
COPY ./minify-js.sh /root/
RUN mkdir /root/prod/
RUN ./minify-js.sh

FROM mavromat/alpine-python:3.6

WORKDIR /root

COPY . ./
RUN rm /root/webapp/render/static/js/custom/*
COPY --from=builder /root/prod/ /root/webapp/render/static/js/custom/

RUN apk update && apk add --no-cache openssl-dev libffi-dev py-openssl sqlite-dev sqlite
RUN pip install --upgrade 'pip<19.0'
RUN pip --no-cache-dir install -r requirements.txt

RUN mkdir -p /etc/artemis/
RUN mkdir -p /var/log/artemis/
COPY ./webapp/configs/* /etc/artemis/

ENTRYPOINT ["./entrypoint"]
