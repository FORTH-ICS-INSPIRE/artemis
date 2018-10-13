FROM jfloff/alpine-python:3.6

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

COPY . ./

RUN apk update && apk add --no-cache openssl-dev libffi-dev py-openssl sqlite-dev sqlite
RUN pip --no-cache-dir install -r requirements.txt
RUN pip --no-cache-dir install gunicorn

RUN mkdir -p /etc/artemis/
RUN mkdir -p /var/log/artemis/
COPY ./webapp/configs/* /etc/artemis/

ENTRYPOINT ["./entrypoint"]
