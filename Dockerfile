FROM python:3

LABEL maintainer="Dimitrios Mavrommatis <jim.mavrommatis@gmail.com>"

RUN apt-get update && \
    apt-get -y install python3-pip

WORKDIR /root

COPY . ./

RUN pip3 --no-cache-dir install -r requirements.txt

RUN curl -sL https://deb.nodesource.com/setup_9.x | bash - && \
    apt-get install -y nodejs build-essential

WORKDIR taps
RUN npm i npm@latest -g && \
    npm install && \
    npm audit fix

WORKDIR ..

ENTRYPOINT ["python3", "artemis.py"]
