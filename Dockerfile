FROM python:3

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install python3-pip rabbitmq-server

WORKDIR /root

COPY . ./

RUN pip3 --no-cache-dir install -r requirements.txt

RUN curl -sL https://deb.nodesource.com/setup_9.x | bash - && \
    apt-get install -y nodejs build-essential

WORKDIR taps
RUN npm i npm@latest -g && \
    npm install && \
    npm audit fix && \
    npm install

WORKDIR ..
RUN mkdir src
WORKDIR src

RUN curl -O https://research.wand.net.nz/software/wandio/wandio-1.0.4.tar.gz && \
    tar zxf wandio-1.0.4.tar.gz
WORKDIR wandio-1.0.4
RUN ./configure && make && make install && ldconfig

WORKDIR ..

RUN curl -O http://bgpstream.caida.org/bundles/caidabgpstreamwebhomepage/dists/bgpstream-1.2.0.tar.gz && \
    tar zxf bgpstream-1.2.0.tar.gz
WORKDIR bgpstream-1.2.0
RUN ./configure && make && make install && ldconfig
RUN pip3 install pybgpstream

WORKDIR ../..

RUN rabbitmq-server -detached

ENTRYPOINT ["bash"]
