#!/bin/sh
i=1
while [ $i -le 10 ]
do
  j=1
  while [ $j -le 50 ]
  do
    origin=$(( $RANDOM % 10 + 1 ))
    gobgp global rib add 192.$i.$j.0/24 -a ipv4 aspath $origin;
    echo "Added prefix 192.$i.$j.0/24 with origin AS$origin";
    gobgp global rib add 2001:db8:$i:$j::/64 -a ipv6 aspath $origin;
    echo "Added prefix 2001:db8:$i:$j::/64 with origin AS$origin";
    j=$((j+1));
  done
  i=$((i+1));
done
