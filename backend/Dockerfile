FROM mavromat/artemis-backend-base:latest
LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root
COPY ./configs/* /etc/artemis/
COPY ./supervisor.d/* /etc/supervisor/conf.d/
COPY entrypoint hasura_init.json Makefile wait-for ./
COPY migrate ./migrate

RUN sed -i 's/bind 127.0.0.1/bind 0.0.0.0/g' /etc/redis.conf && \
    sed -i 's/notify-keyspace-events ""/notify-keyspace-events KEA/g' /etc/redis.conf && \
    sed -i "s;files = /etc/supervisor.d/\*.ini;files = /etc/supervisor/conf.d/\*;g" /etc/supervisord.conf && \
    # backwards compatibility
    ln -s /usr/local/lib/pyenv/versions/3.6.8/bin/python /usr/local/bin && \
    mkdir -p /etc/artemis/ && mkdir -p /var/log/artemis/

COPY requirements.txt ./requirements.txt
RUN pip --no-cache-dir install -r requirements.txt --ignore-installed && \
    pip --no-cache-dir install git+https://github.com/supervisor/supervisor@a0ee8f1026c929ae4d9fc84741924414e8008f49

COPY core ./core

RUN make clean && make -j

ENTRYPOINT ["./entrypoint"]
