#!/usr/bin/env python
import os

import _pybgpstream

KAFKA_HOST = os.getenv("KAFKA_HOST", "openbmp-kafka")
KAFKA_PORT = os.getenv("KAFKA_PORT", "9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "openbmp.bmp_raw")

# create a new bgpstream instance and a reusable bgprecord instance
stream = _pybgpstream.BGPStream()

# set kafka data interface
stream.set_data_interface("kafka")

# set host connection details
stream.set_data_interface_option(
    "kafka", "brokers", "{}:{}".format(KAFKA_HOST, KAFKA_PORT)
)

# set topic
stream.set_data_interface_option("kafka", "topic", KAFKA_TOPIC)

# filter record type
stream.add_filter("record-type", "updates")

# set live mode
stream.set_live_mode()

# start the stream
stream.start()

while True:
    # get next record
    try:
        rec = stream.get_next_record()
    except BaseException:
        continue
    if (rec.status != "valid") or (rec.type != "update"):
        continue

    # get next element
    try:
        elem = rec.get_next_elem()
    except BaseException:
        continue

    while elem:
        if elem.type in {"A", "W"}:
            this_prefix = str(elem.fields["prefix"])
            service = "bgpstreamkafka|{}".format(str(rec.collector))
            type_ = elem.type
            if type_ == "A":
                as_path = elem.fields["as-path"].split(" ")
                communities = [
                    {"asn": int(comm.split(":")[0]), "value": int(comm.split(":")[1])}
                    for comm in elem.fields["communities"]
                ]
            else:
                as_path = []
                communities = []
            timestamp = float(rec.time)
            peer_asn = elem.peer_asn
            msg = {
                "type": type_,
                "timestamp": timestamp,
                "path": as_path,
                "service": service,
                "communities": communities,
                "prefix": this_prefix,
                "peer_asn": peer_asn,
            }
            print(msg)
        try:
            elem = rec.get_next_elem()
        except BaseException:
            continue
