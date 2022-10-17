# Replaying history

ARTEMIS can optionally replay historical records downloaded via tools like BGPStream.
The following steps need to be done for ARTEMIS to replay these records in a streaming fashion:

* Set the `.env` variable `HISTORIC` to true and restart ARTEMIS.
* Collect the files with the BGP updates in a CSV directory. Each file should have the following bgpstream-compatible format:
  ```
  <prefix>|<origin_asn>|<peer_asn>|<blank_separated_as_path>|<project>|<collector>|<update_type_A_or_W>|<bgpstream_community_json_dump>|<timestamp>
  ```
  Note that withdrawal ('W') updates do not need to have the origin asn and as path specified (these can be empty strings), while 'A' updates require all fields. The format for community JSON dumps is as follows:
  ```
  [
    {
      'asn': <asn>,
      'value': <value>
    },
    ...
  ]
  ```
  *For convenience, we have published a [bgpstream-to-csv parser/converter](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/other/bgpstream_retrieve_prefix_records.py) which you can use as follows*:
  ```
  ./other/bgpstream_retrieve_prefix_records.py -p PREFIX -s START_TIME -e END_TIME -o OUTPUT_DIR
  arguments:
  -h, --help                          show this help message and exit
  -p PREFIX, --prefix PREFIX          prefix to check
  -s START_TIME, --start START_TIME   start timestamp (in UNIX epochs)
  -e END_TIME, --end END_TIME         end timestamp (in UNIX epochs)
  -o OUTPUT_DIR, --out_dir OUTPUT_DIR output dir to store the retrieved information
  ```
   Note that you will need the [bgpstream](https://bgpstream.caida.org/docs/install/bgpstream) and [pybgpstream](https://bgpstream.caida.org/docs/install/pybgpstream) and their dependencies installed locally to operate the script. Alternatively, you can map the script in a monitor volume in `docker-compose.yaml` and run it from within the monitor container, after also having properly mapped the directory where the output (i.e., the CSV files with the BGP update records) will be stored.
* Stop ARTEMIS
* In docker-compose, in the `configuration` and `bgpstreamhisttap` container mappings, map the directory containing the CSV files to a proper location, e.g.:
  ```
  ...
  bgpstreamhisttap:
  ...
  volumes:
    ... # other mappings
    - ./csv_dir/:/tmp/csv_dir/
    ... # other mappings
  ...
  configuration:
  ...
  volumes:
    ... # other mappings
    - ./csv_dir/:/tmp/csv_dir/
    ... # other mappings
  ```
* Start ARTEMIS normally
* Edit ARTEMIS configuration to use the extra monitor:
  ```
  monitors:
    ... # other monitors (optional)
    bgpstreamhist: /tmp/csv_dir
  ```
* Activate `bgpstreamhisttap` via the UI
