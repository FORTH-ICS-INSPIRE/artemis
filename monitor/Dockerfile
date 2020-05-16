FROM mavromat/bgpstream-redis:v1.3-bgpstream

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install --no-install-recommends python3-pip supervisor libpq-dev git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root

COPY requirements.txt ./requirements.txt
RUN pip3 --no-cache-dir install -r requirements.txt && \
    pip3 install git+https://github.com/supervisor/supervisor@a0ee8f1026c929ae4d9fc84741924414e8008f49

RUN mkdir -p /etc/artemis/ && \
    mkdir -p /var/log/artemis/

COPY ./configs/* /etc/artemis/
COPY ./supervisor.d/* /etc/supervisor/conf.d/

COPY entrypoint Makefile wait-for ./
COPY core ./core
RUN make clean && make -j

ENTRYPOINT ["./entrypoint"]
