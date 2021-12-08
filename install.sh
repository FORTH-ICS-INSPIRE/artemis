#!/usr/bin/env bash

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
os="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
os="mac"
if [[ `uname -m` == 'arm64' ]]; then
    arch="arm64"
fi
elif [[ "$OSTYPE" == "cygwin" ]]; then
os="cygwin"
elif [[ "$OSTYPE" == "msys" ]]; then
os="msys"
elif [[ "$OSTYPE" == "win32" ]]; then
os="win"
elif [[ "$OSTYPE" == "freebsd"* ]]; then
os="freebsd"
else
os="unknown"
fi

packagesNeeded='git vim'

if [[ "${os}" == 'linux' ]]; then
    if [ -x "$(command -v apk)" ];       then yes | sudo apk add --no-cache $packagesNeeded
    elif [ -x "$(command -v apt-get)" ]; then yes | sudo apt update && sudo apt-get install $packagesNeeded
    elif [ -x "$(command -v dnf)" ];     then yes | sudo dnf install $packagesNeeded
    elif [ -x "$(command -v zypper)" ];  then yes | sudo zypper install $packagesNeeded
    elif [ -x "$(command -v pacman)" ];  then yes | sudo pacman -Syy && sudo pacman -S $packagesNeeded
    elif [ -x "$(command -v yum)" ];     then yes | sudo yum install $packagesNeeded
    else echo -e "${RED}FAILED TO INSTALL PACKAGE: Package manager not found. You must manually install: $packagesNeeded ${NC}">&2; fi
elif [[ "${os}" == 'mac' ]]; then
    brew install $packagesNeeded
fi

git clone https://github.com/FORTH-ICS-INSPIRE/artemis
cd artemis
chmod +x artemis
./artemis install