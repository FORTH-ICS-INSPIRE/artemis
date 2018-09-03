FROM python:3

RUN apt-get update && \
    apt-get -y install python3-pip

WORKDIR /root

COPY . ./

RUN pip3 --no-cache-dir install -r requirements.txt

WORKDIR ..

CMD ["./entrypoint"]

