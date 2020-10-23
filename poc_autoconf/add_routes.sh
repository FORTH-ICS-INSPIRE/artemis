#!/bin/sh
i=1
while [ $i -le 10 ]
do
  j=1
  while [ $j -le 100 ]
  do
    origin=$(( $RANDOM % 10 + 1 ))
    gobgp global rib add 192.$i.$j.0/24 -a ipv4 aspath $origin;
    echo "Added prefix 192.$i.$j.0/24 with origin AS$origin";
    j=$((j+1));
  done
  i=$((i+1));
done
