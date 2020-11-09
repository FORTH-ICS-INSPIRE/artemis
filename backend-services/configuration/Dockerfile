FROM mavromat/artemis-base-images:backend-1.0.0
LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

# backwards compatibility
RUN ln -s /usr/local/lib/pyenv/versions/3.6.8/bin/python /usr/local/bin

COPY requirements.txt ./requirements.txt
RUN pip --no-cache-dir install -r requirements.txt --ignore-installed

RUN mkdir -p /etc/artemis/ && \
    mkdir -p /var/log/artemis/

COPY ./configs/* /etc/artemis/

COPY entrypoint Makefile wait-for ./
COPY core ./core

#RUN make clean && make -j

ENTRYPOINT ["./entrypoint"]
