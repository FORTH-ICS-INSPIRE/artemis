FROM jfloff/alpine-python:3.6

WORKDIR /root

COPY . ./

RUN apk update && apk add --no-cache postgresql-dev
RUN pip --no-cache-dir install -r requirements.txt

ENTRYPOINT ["./entrypoint"]
