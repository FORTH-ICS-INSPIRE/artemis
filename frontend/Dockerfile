FROM python:3-alpine

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

COPY . ./

RUN pip3 --no-cache-dir install -r requirements.txt

ENTRYPOINT ["./entrypoint"]

