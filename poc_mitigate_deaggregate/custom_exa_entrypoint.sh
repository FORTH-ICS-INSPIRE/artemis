#!/usr/bin/env bash
exabgp --fi > exabgp/etc/exabgp/exabgp.env
env exabgp.log.destination=/etc/exabgp/log exabgp.log.routes=true exabgp.daemon.user=home exabgp /home/config/exabgp.conf
