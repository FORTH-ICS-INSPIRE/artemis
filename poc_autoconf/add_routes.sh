#!/bin/sh
i=1
while [ $i -le 10 ]
do
  j=1
  while [ $j -le 100 ]
  do
    gobgp global rib add 192.$i.$j.0/24 -a ipv4;
    echo "Added prefix 192.$i.$j.0/24";
    j=$((j+1));
  done
  i=$((i+1));
done
