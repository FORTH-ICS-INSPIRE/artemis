FROM mavromat/bgpstream-redis:v1.0

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install --no-install-recommends python3-pip supervisor tcl postgresql-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root

COPY . ./
COPY ./testing/configs/ /etc/artemis/
COPY ./testing/supervisor.d/ /etc/supervisor/conf.d/

RUN pip3 --no-cache-dir install -r requirements.txt
RUN pip3 --no-cache-dir install git+https://github.com/supervisor/supervisor@a0ee8f1026c929ae4d9fc84741924414e8008f49
RUN pip3 --no-cache-dir install coverage git+https://github.com/coveralls-clients/coveralls-python@a9b5e3081c8697b60286b9736e956134a2796d5f
RUN mkdir -p /etc/artemis/ && \
    mkdir -p /var/log/artemis/

ENTRYPOINT ["./entrypoint.test"]
