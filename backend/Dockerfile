FROM python:3

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install build-essential zlib1g-dev libbz2-dev libcurl4-openssl-dev python-dev && \
    apt-get -y install python3-pip

WORKDIR /root

COPY . ./

RUN pip3 --no-cache-dir install -r requirements.txt

RUN mkdir src
WORKDIR src

RUN curl -O https://research.wand.net.nz/software/wandio/wandio-1.0.4.tar.gz && \
    tar zxf wandio-1.0.4.tar.gz
WORKDIR wandio-1.0.4
RUN ./configure && make && make install && ldconfig

WORKDIR ..

RUN curl -LO https://github.com/edenhill/librdkafka/archive/v0.11.1.tar.gz && \
    tar zxf v0.11.1.tar.gz
WORKDIR librdkafka-0.11.1
RUN ./configure && make && make install && ldconfig

WORKDIR ..

RUN curl -O http://bgpstream.caida.org/bundles/caidabgpstreamwebhomepage/dists/libbgpstream-2.0.0-beta-5.tar.gz && \
    tar zxf libbgpstream-2.0.0-beta-5.tar.gz
RUN patch -p0 < ../patches/libbgpstream.patch
WORKDIR libbgpstream-2.0.0
RUN ./configure && make && make install && ldconfig

WORKDIR ..

RUN curl -O http://bgpstream.caida.org/bundles/caidabgpstreamwebhomepage/dists/pybgpstream-2.0.0-beta-2.tar.gz && \
    tar zxf pybgpstream-2.0.0-beta-2.tar.gz
WORKDIR pybgpstream-2.0.0
RUN python setup.py build_ext && python setup.py install

WORKDIR ../..

RUN mkdir -p /etc/artemis/
RUN mkdir -p /var/log/artemis/
COPY ./configs/* /etc/artemis/

ENTRYPOINT ["./entrypoint"]

