FROM mavromat/alpine-python:3.6

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apk update && apk add --no-cache supervisor tcl postgresql-client postgresql-dev redis

WORKDIR /root

COPY . ./

RUN pip --no-cache-dir install -r requirements.txt \
    && pip --no-cache-dir install git+https://github.com/supervisor/supervisor@a0ee8f1026c929ae4d9fc84741924414e8008f49 \
    && make clean && make \
    && mkdir -p /etc/artemis/ \
    && mkdir -p /var/log/artemis/

COPY ./configs/* /etc/artemis/

RUN sed -i 's/bind 127.0.0.1/bind 0.0.0.0/g' /etc/redis.conf \
    && sed -i 's/notify-keyspace-events ""/notify-keyspace-events KEA/g' /etc/redis.conf \
    && mkdir -p /etc/supervisor/conf.d/ \
    && sed -i "s;files = /etc/supervisor.d/*.ini;/etc/supervisor/conf.d/*;g" /etc/supervisord.conf \
    # backwards compatibility
    && ln -s /usr/local/lib/pyenv/versions/3.6.8/bin/python /usr/local/bin

ENTRYPOINT ["./entrypoint"]
