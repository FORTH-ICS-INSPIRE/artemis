FROM mavromat/alpine-python:3.6

LABEL maintainer="Vasileios Kotronis <biece89@gmail.com>"

WORKDIR /root

RUN apk update && apk add --no-cache curl jq

COPY . ./

RUN pip --no-cache-dir install -r requirements.txt

ENTRYPOINT ["./entrypoint"]
