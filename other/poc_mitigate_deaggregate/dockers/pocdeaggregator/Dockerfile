FROM mavromat/alpine-python:3.6

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

RUN apk update
COPY requirements.txt /root/
RUN pip --no-cache-dir install -r requirements.txt

COPY entrypoint /root/
COPY wait-for /root/
COPY poc_mitigate_deaggregate.py /root/

ENTRYPOINT ["./entrypoint"]
