# service util functions
import re
import socket
import time

import requests
from artemis_utils.constants import HEALTH_CHECK_TIMEOUT
from artemis_utils.envvars import COMPOSE_PROJECT_NAME
from artemis_utils.envvars import REST_PORT

from . import log


def get_local_ip():
    return socket.gethostbyname(socket.gethostname())


def service_to_ips_and_replicas_in_compose(own_service_name, base_service_name):
    local_ip = get_local_ip()
    service_to_ips_and_replicas_set = set([])
    addr_infos = socket.getaddrinfo(base_service_name, REST_PORT)
    for addr_info in addr_infos:
        af, sock_type, proto, canon_name, sa = addr_info
        replica_ip = sa[0]
        # do not include yourself
        if base_service_name == own_service_name and replica_ip == local_ip:
            continue
        replica_host_by_addr = socket.gethostbyaddr(replica_ip)[0]
        replica_name_match = re.match(
            r"^"
            + re.escape(COMPOSE_PROJECT_NAME)
            + r"_"
            + re.escape(base_service_name)
            + r"_(\d+)",
            replica_host_by_addr,
        )
        replica_name = "{}-{}".format(base_service_name, replica_name_match.group(1))
        service_to_ips_and_replicas_set.add((replica_name, replica_ip))
    return service_to_ips_and_replicas_set


def service_to_ips_and_replicas_in_k8s(base_service_name):
    from kubernetes import client, config

    service_to_ips_and_replicas_set = set([])
    config.load_incluster_config()
    current_namespace = open(
        "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    ).read()
    v1 = client.CoreV1Api()
    try:
        endpoints = v1.read_namespaced_endpoints_with_http_info(
            base_service_name, current_namespace, _return_http_data_only=True
        ).to_dict()
        for entry in endpoints["subsets"][0]["addresses"]:
            replica_name = entry["target_ref"]["name"]
            replica_ip = entry["ip"]
            service_to_ips_and_replicas_set.add((replica_name, replica_ip))
    except Exception as e:
        log.exception(e)

    return service_to_ips_and_replicas_set


def wait_data_worker_dependencies(data_worker_dependencies):
    while True:
        met_deps = set()
        unmet_deps = set()
        for service in data_worker_dependencies:
            try:
                r = requests.get(
                    "http://{}:{}/health".format(service, REST_PORT),
                    timeout=HEALTH_CHECK_TIMEOUT,
                )
                status = True if r.json()["status"] == "running" else False
                if not status:
                    unmet_deps.add(service)
                else:
                    met_deps.add(service)
            except Exception:
                unmet_deps.add(service)
        if len(unmet_deps) == 0:
            log.info(
                "all needed data workers started: {}".format(data_worker_dependencies)
            )
            break
        else:
            log.info(
                "'{}' data workers started, waiting for: '{}'".format(
                    met_deps, unmet_deps
                )
            )
        time.sleep(1)
