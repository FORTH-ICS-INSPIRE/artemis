FROM python:3

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install python3-pip

WORKDIR /root

COPY . ./

RUN pip3 --no-cache-dir install -r requirements.txt

ENTRYPOINT ["./entrypoint"]

