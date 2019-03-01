FROM java:openjdk-8-jre-alpine as builder
LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

RUN apk add --no-cache openssl && \
    wget https://dl.google.com/closure-compiler/compiler-latest.tar.gz && \
    tar -xzvf compiler-latest.tar.gz

COPY ./webapp/static/js/custom/ /root/
COPY ./minify-js.sh /root/
RUN mkdir /root/prod/
RUN ./minify-js.sh

FROM jfloff/alpine-python:3.6

WORKDIR /root

COPY . ./
RUN rm /root/webapp/static/js/custom/*
COPY --from=builder /root/prod/ /root/webapp/static/js/custom/

RUN apk update && apk add --no-cache openssl-dev libffi-dev py-openssl sqlite-dev sqlite curl
RUN pip install --upgrade 'pip<19.0'
RUN pip --no-cache-dir install -r requirements.txt

RUN mkdir /root/src

WORKDIR /root/src

RUN curl -LO http://pyyaml.org/download/libyaml/yaml-0.2.1.tar.gz && \
    tar xzf yaml-0.2.1.tar.gz
WORKDIR /root/src/yaml-0.2.1
RUN ./configure && make && make install

WORKDIR /root/src/

RUN curl -O https://pyyaml.org/download/pyyaml/PyYAML-3.13.tar.gz && \
    tar xzf PyYAML-3.13.tar.gz
WORKDIR /root/src/PyYAML-3.13
RUN python setup.py --with-libyaml install

WORKDIR /root

RUN mkdir -p /etc/artemis/
RUN mkdir -p /var/log/artemis/
COPY ./webapp/configs/* /etc/artemis/

ENTRYPOINT ["./entrypoint"]
