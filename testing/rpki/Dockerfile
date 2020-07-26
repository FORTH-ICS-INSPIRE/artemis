FROM mavromat/alpine-python:3.6

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

WORKDIR /root

COPY . ./

RUN apk update && apk add --no-cache postgresql-dev git libffi-dev cmake libssh

RUN git clone -b v0.7.0 --depth 1 https://github.com/rtrlib/rtrlib.git
WORKDIR /root/rtrlib
RUN cmake -D CMAKE_BUILD_TYPE=Release .
RUN make -j && make install
WORKDIR /root

COPY requirements.txt /root/
RUN pip --no-cache-dir install -r requirements.txt

RUN ln -s /usr/local/lib64/librtr.so /usr/local/lib/librtr.so \
    && ln -s /usr/local/lib64/librtr.so.0 /usr/local/lib/librtr.so.0 \
    && ln -s /usr/local/lib64/librtr.so.0.7.0 /usr/local/lib/librtr.so.0.7.0

RUN git clone https://github.com/rtrlib/python-binding.git
WORKDIR /root/python-binding
RUN git checkout 2ade90eddd1895515948481136c8197e9cada128
RUN python setup.py build && python setup.py install
WORKDIR /root

ENTRYPOINT ["./entrypoint"]
