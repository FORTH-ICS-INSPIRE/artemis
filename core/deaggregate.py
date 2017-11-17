from netaddr import IPNetwork

class Deaggr:

    def __init__(self, prefix, max_deaggr):

        self.max_deaggr = max_deaggr
        self.__prefix = prefix
        self.__subprefixes = []
        self.__calc_subprefixes()


    def __calc_subprefixes(self):
        net = IPNetwork(self.__prefix)
        self.__subprefixes = list()
        # if new prefix len exceeds ipv4 or ipv6 max lengths
        if net.prefixlen < self.max_deaggr:
            new_prefixlen = net.prefixlen + 1
            self.__subprefixes = net.subnet(new_prefixlen)


    def print_subprefixes(self):
        for subprefix in self.__subprefixes:
            print(subprefix)


    def get_subprefixes(self):
        prefixes = []
        for prefix in self.__subprefixes:
            prefixes.append(str(prefix))

        return prefixes
