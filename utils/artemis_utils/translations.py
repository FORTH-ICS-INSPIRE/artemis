# translation functions
import re
from ipaddress import ip_network as str2ip

import requests
from artemis_utils.constants import ASN_REGEX
from artemis_utils.constants import RIPE_ASSET_REGEX

from . import ArtemisError


def valid_prefix(input_prefix):
    try:
        str2ip(input_prefix)
    except Exception:
        return False
    return True


def calculate_more_specifics(prefix, min_length, max_length):
    for prefix_length in range(min_length, max_length + 1):
        for sub_prefix in prefix.subnets(new_prefix=prefix_length):
            yield str(sub_prefix)


def translate_rfc2622(input_prefix, just_match=False):
    """
    :param input_prefix: (str) input IPv4/IPv6 prefix that
    should be translated according to RFC2622
    :param just_match: (bool) check only if the prefix
    has matched instead of translating
    :return: output_prefixes: (iterator of str) output IPv4/IPv6 prefixes,
    if not just_match, otherwise True or False
    """

    # ^- is the exclusive more specifics operator; it stands for the more
    #    specifics of the address prefix excluding the address prefix
    #    itself.  For example, 128.9.0.0/16^- contains all the more
    #    specifics of 128.9.0.0/16 excluding 128.9.0.0/16.
    reg_exclusive = re.match(r"^(\S*)\^-$", input_prefix)
    if reg_exclusive:
        matched_prefix = reg_exclusive.group(1)
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = matched_prefix_ip.prefixlen + 1
            max_length = matched_prefix_ip.max_prefixlen
            if just_match:
                return True
            return calculate_more_specifics(matched_prefix_ip, min_length, max_length)

    # ^+ is the inclusive more specifics operator; it stands for the more
    #    specifics of the address prefix including the address prefix
    #    itself.  For example, 5.0.0.0/8^+ contains all the more specifics
    #    of 5.0.0.0/8 including 5.0.0.0/8.
    reg_inclusive = re.match(r"^(\S*)\^\+$", input_prefix)
    if reg_inclusive:
        matched_prefix = reg_inclusive.group(1)
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = matched_prefix_ip.prefixlen
            max_length = matched_prefix_ip.max_prefixlen
            if just_match:
                return True
            return calculate_more_specifics(matched_prefix_ip, min_length, max_length)

    # ^n where n is an integer, stands for all the length n specifics of
    #    the address prefix.  For example, 30.0.0.0/8^16 contains all the
    #    more specifics of 30.0.0.0/8 which are of length 16 such as
    #    30.9.0.0/16.
    reg_n = re.match(r"^(\S*)\^(\d+)$", input_prefix)
    if reg_n:
        matched_prefix = reg_n.group(1)
        length = int(reg_n.group(2))
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = length
            max_length = length
            if min_length < matched_prefix_ip.prefixlen:
                raise ArtemisError("invalid-n-small", input_prefix)
            if max_length > matched_prefix_ip.max_prefixlen:
                raise ArtemisError("invalid-n-large", input_prefix)
            if just_match:
                return True
            return list(
                map(
                    str,
                    calculate_more_specifics(matched_prefix_ip, min_length, max_length),
                )
            )

    # ^n-m where n and m are integers, stands for all the length n to
    #      length m specifics of the address prefix.  For example,
    #      30.0.0.0/8^24-32 contains all the more specifics of 30.0.0.0/8
    #      which are of length 24 to 32 such as 30.9.9.96/28.
    reg_n_m = re.match(r"^(\S*)\^(\d+)-(\d+)$", input_prefix)
    if reg_n_m:
        matched_prefix = reg_n_m.group(1)
        min_length = int(reg_n_m.group(2))
        max_length = int(reg_n_m.group(3))
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            if min_length < matched_prefix_ip.prefixlen:
                raise ArtemisError("invalid-n-small", input_prefix)
            if max_length > matched_prefix_ip.max_prefixlen:
                raise ArtemisError("invalid-n-large", input_prefix)
            if just_match:
                return True
            return calculate_more_specifics(matched_prefix_ip, min_length, max_length)

    # nothing has matched
    if just_match:
        return False

    return [input_prefix]


def translate_asn_range(asn_range, just_match=False):
    """
    :param <str> asn_range: <start_asn>-<end_asn>
    :param <bool> just_match: check only if the prefix
    has matched instead of translating
    :return: the list of ASNs corresponding to that range
    """
    reg_range = re.match(r"(\d+)\s*-\s*(\d+)", str(asn_range))
    if reg_range:
        start_asn = int(reg_range.group(1))
        end_asn = int(reg_range.group(2))
        if start_asn > end_asn:
            raise ArtemisError("end-asn before start-asn", asn_range)
        if just_match:
            return True
        return list(range(start_asn, end_asn + 1))

    # nothing has matched
    if just_match:
        return False

    return [asn_range]


def translate_as_set(as_set_id, just_match=False):
    """
    :param as_set_id: the ID of the AS-SET as present in the RIPE database (with a prefix in front for disambiguation)
    :param <bool> just_match: check only if the as_set name has matched instead of translating
    :return: the list of ASes that are present in the set
    """
    as_set = ""
    as_set_match = re.match(RIPE_ASSET_REGEX, as_set_id)
    if as_set_match:
        if just_match:
            return True
        try:
            as_set = as_set_match.group(1)
            as_members = set()
            response = requests.get(
                "https://stat.ripe.net/data/historical-whois/data.json?resource=as-set:{}".format(
                    as_set
                ),
                timeout=10,
            )
            json_response = response.json()
            for obj in json_response["data"]["objects"]:
                if obj["type"] == "as-set" and obj["latest"]:
                    for attr in obj["attributes"]:
                        if attr["attribute"] == "members":
                            value = attr["value"]
                            asn_match = re.match(ASN_REGEX, value)
                            if asn_match:
                                asn = int(asn_match.group(1))
                                as_members.add(asn)
                            else:
                                return {
                                    "success": False,
                                    "payload": {},
                                    "error": "invalid-asn-{}-in-as-set-{}".format(
                                        value, as_set
                                    ),
                                }
                else:
                    continue
            if as_members:
                return {
                    "success": True,
                    "payload": {"as_members": sorted(list(as_members))},
                    "error": False,
                }
            return {
                "success": False,
                "payload": {},
                "error": "empty-as-set-{}".format(as_set),
            }
        except Exception:
            return {
                "success": False,
                "payload": {},
                "error": "error-as-set-resolution-{}".format(as_set),
            }
    return False
