# service util functions
import re
import socket
import time
import dns.resolver
import dns.query

import requests
from artemis_utils.constants import HEALTH_CHECK_TIMEOUT
from artemis_utils.envvars import COMPOSE_PROJECT_NAME
from artemis_utils.envvars import REST_PORT

from . import log


def get_local_ip():
    return socket.gethostbyname(socket.gethostname())

def resolve_dns(query:str, rtype = ['AAAA','A'], timeout:int = 2)->list:
  if isinstance(rtype, str):
    rtype.upper()
    rlist = rtype.split()
  else:
    rlist = [t.upper() for t in rtype]

  def lookup(query, rtype:str, timeout:int = 2)->list:
    resolver = dns.resolver.Resolver()
    if rtype == "PTR":
      query = dns.reversename.from_address(query)
    msg = dns.message.make_query(query,rtype)
    for dns_server in resolver.nameservers:
      try:
        resp = dns.query.udp(msg,dns_server,timeout=timeout)
        if resp.answer:
          return [str(a) for a in resp.answer[0] ]
      except Exception as e:
         log.error("error:",dns_server, e)
    return []

  #podman responds with an A record if you query with AAAA and AAAA does not exist.
  #for this reason, we must remove dupliicates.
  result = []
  result += [r for qt in rlist for r in (lookup(query, qt, timeout)) if r not in result ]
  return result

def service_to_ips_and_replicas_in_compose(own_service_name, base_service_name):
    local_ip = get_local_ip()
    address_regexp = re.compile ('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
    service_to_ips_and_replicas_set = set([])
    addr_infos = resolve_dns(base_service_name)
    for replica_ip in addr_infos:
        # do not include yourself
        if base_service_name == own_service_name and replica_ip == local_ip:
            continue
        ptr = resolve_dns(replica_ip, 'PTR')
        for replica_host_by_addr in ptr:
          replica_name_match = re.match(
            r"^"
            + re.escape(COMPOSE_PROJECT_NAME)
            + r"[_|-]"
            + re.escape(base_service_name)
            + r"[_|-](\d+)",
            replica_host_by_addr,
          )
          if replica_name_match:
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
