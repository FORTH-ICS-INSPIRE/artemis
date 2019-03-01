FROM mavromat/bgpstream-redis:v1.0

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install --no-install-recommends python3-pip cron supervisor tcl postgresql-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root

RUN mkdir /root/src
WORKDIR /root/src

RUN curl -LO http://pyyaml.org/download/libyaml/yaml-0.2.1.tar.gz && \
    tar xzf yaml-0.2.1.tar.gz
WORKDIR /root/src/yaml-0.2.1
RUN ./configure && make && make install

WORKDIR /root/src/

RUN curl -O https://pyyaml.org/download/pyyaml/PyYAML-3.13.tar.gz && \
    tar xzf PyYAML-3.13.tar.gz
WORKDIR /root/src/PyYAML-3.13
RUN python setup.py --with-libyaml install

WORKDIR /root

COPY . ./

RUN pip3 --no-cache-dir install -r requirements.txt
RUN pip3 install git+https://github.com/supervisor/supervisor@a0ee8f1026c929ae4d9fc84741924414e8008f49
RUN make clean && make
RUN mkdir -p /etc/artemis/ && \
    mkdir -p /var/log/artemis/

COPY ./configs/* /etc/artemis/

ENTRYPOINT ["./entrypoint"]
