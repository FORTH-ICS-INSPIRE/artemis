FROM jfloff/alpine-python:3.6

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

RUN apk update && apk add --no-cache postgresql-dev
COPY requirements.txt /root/
RUN pip --no-cache-dir install -r requirements.txt

COPY entrypoint /root/
COPY wait-for /root/
COPY testfiles /root/
COPY tester.py /root/

ENTRYPOINT ["./entrypoint"]
