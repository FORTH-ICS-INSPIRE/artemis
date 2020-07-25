#!/bin/sh

gobgpd -f /etc/gobgp/gobgp.conf &

sleep 5;

while true; do
  echo "Announce.."
  gobgp global rib add 11.0.1.0/24
  sleep 10;

  echo "Withdraw.."
  gobgp global rib del 11.0.1.0/24
  sleep 10;
done
