FROM mavromat/artemis-base-images:backend-1.0.0
LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root
COPY entrypoint wait-for ./

RUN sed -i 's/bind 127.0.0.1/bind 0.0.0.0/g' /etc/redis.conf && \
    sed -i 's/notify-keyspace-events ""/notify-keyspace-events KEA/g' /etc/redis.conf && \
    # backwards compatibility
    ln -s /usr/local/lib/pyenv/versions/3.6.8/bin/python /usr/local/bin

COPY requirements.txt ./requirements.txt
RUN pip --no-cache-dir install -r requirements.txt --ignore-installed

ENTRYPOINT ["./entrypoint"]
