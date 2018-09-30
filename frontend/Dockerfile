FROM jfloff/alpine-python:3.6

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

COPY . ./

RUN apk update && apk add --no-cache openssl-dev libffi-dev py-openssl
RUN pip --no-cache-dir install -r requirements.txt

ENTRYPOINT ["./entrypoint"]

