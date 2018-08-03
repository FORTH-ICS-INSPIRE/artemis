#!/bin/sh
python emit.py bgp_update update '{"type":"A", "as_path": [0,1,2,3], "prefix": "139.91.0.0/24", "timestamp": 0}'
python emit.py bgp_update update '{"type":"A", "as_path": [0,1,2,3], "prefix": "139.91.0.0/24", "timestamp": 1}'
python emit.py bgp_update update '{"type":"A", "as_path": [0,1,2,3], "prefix": "139.91.0.0/24", "timestamp": 2}'
python emit.py bgp_update update '{"type":"A", "as_path": [0,1,2,3], "prefix": "139.91.0.0/24", "timestamp": 3}'
python emit.py config_notify notification "{}"
python emit.py bgp_update update '{"type":"A", "as_path": [0,1,2,3], "prefix": "139.91.0.0/24", "timestamp": 4}'
