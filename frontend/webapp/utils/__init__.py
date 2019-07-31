import os

# import re
# from ipaddress import ip_network as str2ip

RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
API_HOST = os.getenv("API_HOST", "postgrest")
API_PORT = os.getenv("API_PORT", 3000)
SUPERVISOR_HOST = os.getenv("SUPERVISOR_HOST", "backend")
SUPERVISOR_PORT = os.getenv("SUPERVISOR_PORT", 9001)
MON_SUPERVISOR_HOST = os.getenv("MON_SUPERVISOR_HOST", "monitor")
MON_SUPERVISOR_PORT = os.getenv("MON_SUPERVISOR_PORT", 9001)

RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
    RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
)
SUPERVISOR_URI = "http://{}:{}/RPC2".format(SUPERVISOR_HOST, SUPERVISOR_PORT)
MON_SUPERVISOR_URI = "http://{}:{}/RPC2".format(
    MON_SUPERVISOR_HOST, MON_SUPERVISOR_PORT
)
API_URI = "http://{}:{}".format(API_HOST, API_PORT)


def flatten(items, seqtypes=(list, tuple)):
    res = []
    if not isinstance(items, seqtypes):
        return [items]
    for item in items:
        if isinstance(item, seqtypes):
            res += flatten(item)
        else:
            res.append(item)
    return res


# def calculate_more_specifics(prefix, min_length, max_length):
#     prefix_list = []
#     for prefix_length in range(min_length, max_length + 1):
#         prefix_list.extend(prefix.subnets(new_prefix=prefix_length))
#     return prefix_list
#
#
# def translate_rfc2622(input_prefix, just_match=False):
#     """
#     :param input_prefix: (str) input IPv4/IPv6 prefix that
#     should be translated according to RFC2622
#     :param just_match: (bool) check only if the prefix
#     has matched instead of translating
#     :return: output_prefixes: (list of str) output IPv4/IPv6 prefixes,
#     if not just_match, otherwise True or False
#     """
#
#     # ^- is the exclusive more specifics operator; it stands for the more
#     #    specifics of the address prefix excluding the address prefix
#     #    itself.  For example, 128.9.0.0/16^- contains all the more
#     #    specifics of 128.9.0.0/16 excluding 128.9.0.0/16.
#     reg_exclusive = re.match(r"^(\S*)\^-$", input_prefix)
#     if reg_exclusive:
#         matched_prefix = reg_exclusive.group(1)
#         matched_prefix_ip = str2ip(matched_prefix)
#         min_length = matched_prefix_ip.prefixlen + 1
#         max_length = matched_prefix_ip.max_prefixlen
#         if just_match:
#             return True
#         return list(
#             map(
#                 str, calculate_more_specifics(matched_prefix_ip, min_length, max_length)
#             )
#         )
#
#     # ^+ is the inclusive more specifics operator; it stands for the more
#     #    specifics of the address prefix including the address prefix
#     #    itself.  For example, 5.0.0.0/8^+ contains all the more specifics
#     #    of 5.0.0.0/8 including 5.0.0.0/8.
#     reg_inclusive = re.match(r"^(\S*)\^\+$", input_prefix)
#     if reg_inclusive:
#         matched_prefix = reg_inclusive.group(1)
#         matched_prefix_ip = str2ip(matched_prefix)
#         min_length = matched_prefix_ip.prefixlen
#         max_length = matched_prefix_ip.max_prefixlen
#         if just_match:
#             return True
#         return list(
#             map(
#                 str, calculate_more_specifics(matched_prefix_ip, min_length, max_length)
#             )
#         )
#
#     # ^n where n is an integer, stands for all the length n specifics of
#     #    the address prefix.  For example, 30.0.0.0/8^16 contains all the
#     #    more specifics of 30.0.0.0/8 which are of length 16 such as
#     #    30.9.0.0/16.
#     reg_n = re.match(r"^(\S*)\^(\d+)$", input_prefix)
#     if reg_n:
#         matched_prefix = reg_n.group(1)
#         length = int(reg_n.group(2))
#         matched_prefix_ip = str2ip(matched_prefix)
#         min_length = length
#         max_length = length
#         if just_match:
#             return True
#         return list(
#             map(
#                 str, calculate_more_specifics(matched_prefix_ip, min_length, max_length)
#             )
#         )
#
#     # ^n-m where n and m are integers, stands for all the length n to
#     #      length m specifics of the address prefix.  For example,
#     #      30.0.0.0/8^24-32 contains all the more specifics of 30.0.0.0/8
#     #      which are of length 24 to 32 such as 30.9.9.96/28.
#     reg_n_m = re.match(r"^(\S*)\^(\d+)-(\d+)$", input_prefix)
#     if reg_n_m:
#         matched_prefix = reg_n_m.group(1)
#         min_length = int(reg_n_m.group(2))
#         max_length = int(reg_n_m.group(3))
#         matched_prefix_ip = str2ip(matched_prefix)
#         if just_match:
#             return True
#         return list(
#             map(
#                 str, calculate_more_specifics(matched_prefix_ip, min_length, max_length)
#             )
#         )
#
#     # nothing has matched
#     if just_match:
#         return False
#
#     return [input_prefix]
