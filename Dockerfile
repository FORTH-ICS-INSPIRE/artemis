# FROM python:3
# LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"
# RUN apt-get update && \
#     apt-get -y install python3-pip
# WORKDIR /root
# COPY . ./
# RUN pip3 --no-cache-dir install -r requirements.txt

FROM python:3.6-alpine
WORKDIR /root
COPY . ./
RUN apk update && apk add --no-cache gcc musl-dev
RUN pip --no-cache-dir install -r requirements.txt
ENTRYPOINT ["python3", "artemis.py"]

# RUN mkdir src
# WORKDIR src
#
# RUN curl -O https://research.wand.net.nz/software/wandio/wandio-1.0.4.tar.gz && \
#     tar zxf wandio-1.0.4.tar.gz
# WORKDIR wandio-1.0.4
# RUN ./configure && make && make install && ldconfig
#
# WORKDIR ..
#
# RUN curl -O http://bgpstream.caida.org/bundles/caidabgpstreamwebhomepage/dists/bgpstream-1.2.0.tar.gz && \
#     tar zxf bgpstream-1.2.0.tar.gz
# WORKDIR bgpstream-1.2.0
# RUN ./configure && make && make install && ldconfig
# RUN pip3 install pybgpstream
#
# WORKDIR ../..
