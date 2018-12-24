FROM python:3.6.7

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install build-essential zlib1g-dev libbz2-dev libcurl4-openssl-dev python-dev && \
    apt-get -y install python3-pip cron supervisor tcl

WORKDIR /root

COPY . ./

RUN pip3 --no-cache-dir install -r requirements.txt
RUN pip3 install git+https://github.com/supervisor/supervisor@master
RUN make clean && make

RUN mkdir src
WORKDIR /root/src

RUN curl -O https://research.wand.net.nz/software/wandio/wandio-1.0.4.tar.gz && \
    tar zxf wandio-1.0.4.tar.gz
WORKDIR /root/src/wandio-1.0.4
RUN ./configure && make && make install && ldconfig

WORKDIR /root/src

RUN curl -LO https://github.com/edenhill/librdkafka/archive/v0.11.1.tar.gz && \
    tar zxf v0.11.1.tar.gz
WORKDIR /root/src/librdkafka-0.11.1
RUN ./configure && make && make install && ldconfig

WORKDIR /root/src

RUN curl -O http://bgpstream.caida.org/bundles/caidabgpstreamwebhomepage/dists/libbgpstream-2.0.0-beta-5.tar.gz && \
    tar zxf libbgpstream-2.0.0-beta-5.tar.gz
RUN patch -p0 < ../patches/libbgpstream.patch
WORKDIR /root/src/libbgpstream-2.0.0
RUN ./configure && make && make install && ldconfig

WORKDIR /root/src

RUN curl -O http://bgpstream.caida.org/bundles/caidabgpstreamwebhomepage/dists/pybgpstream-2.0.0-beta-2.tar.gz && \
    tar zxf pybgpstream-2.0.0-beta-2.tar.gz
WORKDIR /root/src/pybgpstream-2.0.0
RUN python setup.py build_ext && python setup.py install

WORKDIR /root/src

RUN curl -O http://download.redis.io/redis-stable.tar.gz && \
    tar xzvf redis-stable.tar.gz
WORKDIR /root/src/redis-stable
RUN make && make install && ldconfig && \
    mkdir -p /etc/redis/ && cp redis.conf /etc/redis/

WORKDIR /root

RUN mkdir -p /etc/artemis/ && \
    mkdir -p /var/log/artemis/ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY ./configs/* /etc/artemis/

ENTRYPOINT ["./entrypoint"]
