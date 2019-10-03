FROM mavromat/alpine-python:3.6

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

RUN apk update && apk add --no-cache curl jq

COPY . ./

RUN pip --no-cache-dir install -r requirements.txt

ENTRYPOINT ["./entrypoint"]
