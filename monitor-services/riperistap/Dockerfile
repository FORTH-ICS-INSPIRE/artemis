FROM mavromat/artemis-base-images:monitor-1.0.3
LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install --no-install-recommends python3-pip libpq-dev git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root

COPY requirements.txt ./requirements.txt
RUN pip3 --no-cache-dir install -r requirements.txt

RUN mkdir -p /etc/artemis/ && \
    mkdir -p /var/log/artemis/

COPY entrypoint Makefile wait-for ./
COPY core ./core

RUN make clean && make -j

ENTRYPOINT ["./entrypoint"]
