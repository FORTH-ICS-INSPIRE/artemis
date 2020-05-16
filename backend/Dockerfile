FROM mavromat/alpine-python:3.6

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apk update && apk add --no-cache supervisor tcl postgresql-client postgresql-dev redis curl git libffi-dev cmake libssh

WORKDIR /root
# Install rtlib
RUN git clone -b v0.7.0 --depth 1 https://github.com/rtrlib/rtrlib.git && \
    cd rtrlib && \
    cmake -D CMAKE_BUILD_TYPE=Release . && \
    make -j 4 && make install && \
    ln -s /usr/local/lib64/librtr.so /usr/local/lib/librtr.so && \
    ln -s /usr/local/lib64/librtr.so.0 /usr/local/lib/librtr.so.0 && \
    ln -s /usr/local/lib64/librtr.so.0.7.0 /usr/local/lib/librtr.so.0.7.0 && \
    git clone https://github.com/rtrlib/python-binding.git && \
    cd python-binding && \
    git checkout 2ade90eddd1895515948481136c8197e9cada128 && \
    python setup.py build install

WORKDIR /root
COPY ./configs/* /etc/artemis/
COPY ./supervisor.d/* /etc/supervisor/conf.d/
COPY requirements.txt ./requirements.txt

RUN sed -i 's/bind 127.0.0.1/bind 0.0.0.0/g' /etc/redis.conf && \
    sed -i 's/notify-keyspace-events ""/notify-keyspace-events KEA/g' /etc/redis.conf && \
    mkdir -p /etc/supervisor/conf.d/ && \
    sed -i "s;files = /etc/supervisor.d/\*.ini;files = /etc/supervisor/conf.d/\*;g" /etc/supervisord.conf && \
    # backwards compatibility
    ln -s /usr/local/lib/pyenv/versions/3.6.8/bin/python /usr/local/bin && \
    mkdir -p /etc/artemis/ && \
    mkdir -p /var/log/artemis/

RUN pip --no-cache-dir install -r requirements.txt --ignore-installed && \
    pip --no-cache-dir install git+https://github.com/supervisor/supervisor@a0ee8f1026c929ae4d9fc84741924414e8008f49

COPY hasura_metadata entrypoint hasura_init.json Makefile wait-for ./
COPY migrate ./migrate
COPY core ./core

RUN make clean && make -j

ENTRYPOINT ["./entrypoint"]
