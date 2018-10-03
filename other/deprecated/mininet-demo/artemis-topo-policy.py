#!/usr/bin/python

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import setLogLevel, info, debug
from mininet.node import Host, OVSSwitch
from os.path import expanduser


HOME = expanduser("~")
QUAGGA_DIR = '/usr/lib/quagga'
# Must exist and be owned by quagga user (quagga:quagga by default on Ubuntu)
QUAGGA_RUN_DIR = '/var/run/quagga'
EXABGP_RUN_EXE = '%s/exabgp/sbin/exabgp' % str(HOME)
CONFIG_DIR = 'configs_policy/'


# instance of Quagga Router
# set interfaces and IPs
class QuaggaRouter(Host):

    def __init__(self, name, quaggaConfFile, zebraConfFile,
                 intfDict, greDict, *args, **kwargs):
        Host.__init__(self, name, *args, **kwargs)

        self.quaggaConfFile = quaggaConfFile
        self.zebraConfFile = zebraConfFile
        self.intfDict = intfDict
        self.greDict = greDict

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        self.cmd('sysctl net.ipv4.ip_forward=1')

        for intf, attrs in self.intfDict.items():
            self.cmd('ip addr flush dev %s' % intf)
            if 'mac' in attrs:
                self.cmd('ip link set %s down' % intf)
                self.cmd('ip link set %s address %s' % (intf, attrs['mac']))
                self.cmd('ip link set %s up ' % intf)
            for addr in attrs['ipAddrs']:
                self.cmd('ip addr add %s dev %s' % (addr, intf))
            self.cmd('sysctl net.ipv4.conf.%s.rp_filter=0' % intf)

        self.cmd('/usr/lib/quagga/zebra -d -f %s -z %s/zebra%s.api -i %s/zebra%s.pid' %
                 (self.zebraConfFile, QUAGGA_RUN_DIR, self.name, QUAGGA_RUN_DIR, self.name))
        self.cmd('/usr/lib/quagga/bgpd -d -f %s -z %s/zebra%s.api -i %s/bgpd%s.pid' %
                 (self.quaggaConfFile, QUAGGA_RUN_DIR, self.name, QUAGGA_RUN_DIR, self.name))

        # http://ask.xmodulo.com/create-gre-tunnel-linux.html
        if self.greDict is not None:
            for gre_iface, gre_params in self.greDict.items():
                if 'local' in gre_params and 'remote' in gre_params and 'ip' in gre_params:
                    self.cmd('ip link set %s down' % gre_iface)
                    self.cmd('ip tunnel del %s' % gre_iface)
                    self.cmd('ip tunnel add %s mode gre remote %s local %s ttl 255' % (gre_iface,
                                                                                       gre_params['remote'],
                                                                                       gre_params['local']))
                    self.cmd('ip link set %s up' % gre_iface)
                    self.cmd(
                        'ip addr add %s dev %s' %
                        (gre_params['ip'], gre_iface))
                    self.cmd('sysctl net.ipv4.conf.%s.rp_filter=0' % gre_iface)

        self.cmd('sysctl net.ipv4.conf.all.rp_filter=0')

    def terminate(self):
        self.cmd("ps ax | egrep 'bgpd%s.pid|zebra%s.pid' | awk '{print $1}' | xargs kill" % (
            self.name, self.name))

        Host.terminate(self)


# instance of ExaBGP router
# set interfaces and IPs
class ExaBGPRouter(Host):

    def __init__(self, name, exaBGPconf, intfDict, *args, **kwargs):
        Host.__init__(self, name, *args, **kwargs)

        self.exaBGPconf = exaBGPconf
        self.intfDict = intfDict

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        self.cmd('sysctl net.ipv4.ip_forward=1')

        for intf, attrs in self.intfDict.items():
            self.cmd('ip addr flush dev %s' % intf)
            if 'mac' in attrs:
                self.cmd('ip link set %s down' % intf)
                self.cmd('ip link set %s address %s' % (intf, attrs['mac']))
                self.cmd('ip link set %s up ' % intf)
            for addr in attrs['ipAddrs']:
                self.cmd('ip addr add %s dev %s' % (addr, intf))

        self.cmd('%s %s > /dev/null 2> %s.log &' %
                 (EXABGP_RUN_EXE, self.exaBGPconf, self.name))

    def terminate(self):
        self.cmd(
            "ps ax | egrep 'lib/exabgp/application/bgp.py' | awk '{print $1}' | xargs kill")
        self.cmd(
            "ps ax | egrep 'server.py' | awk '{print $1}' | xargs kill")
        Host.terminate(self)


# instance of artemis host
class Artemis(Host):

    def __init__(self, name, intfDict, *args, **kwargs):
        Host.__init__(self, name, *args, **kwargs)

        self.intfDict = intfDict

    def config(self, **kwargs):
        Host.config(self, **kwargs)

        for intf, attrs in self.intfDict.items():
            self.cmd('ip addr flush dev %s' % intf)
            if 'mac' in attrs:
                self.cmd('ip link set %s down' % intf)
                self.cmd('ip link set %s address %s' % (intf, attrs['mac']))
                self.cmd('ip link set %s up ' % intf)
            for addr in attrs['ipAddrs']:
                self.cmd('ip addr add %s dev %s' % (addr, intf))


# instance of Layer-2 switch
class L2Switch(OVSSwitch):

    def start(self, controllers):
        return OVSSwitch.start(self, [])


# build the demo ARTEMIS topology
class ArtemisTopo(Topo):
    "Artemis tutorial topology"

    def build(self):
        zebraConf = '%szebra.conf' % CONFIG_DIR

        # R1 router, AS65001 (artemis)
        quaggaConf = '%sR1-quagga.conf' % CONFIG_DIR
        name = 'R1'
        # management interface (facing artemis)
        eth0 = {
            'ipAddrs': ['192.168.101.1/30']
        }
        # internal interface (facing h1 and exabgp rc 65001)
        eth1 = {
            'ipAddrs': ['10.0.0.1/8']
        }
        # external interface (facing R2)
        eth2 = {
            'ipAddrs': ['150.1.1.1/30']
        }
        intfs = {
            '%s-eth0' % name: eth0,
            '%s-eth1' % name: eth1,
            '%s-eth2' % name: eth2
        }
        greDict = {
            'gre1': {
                'local': '150.1.1.1',
                'remote': '150.1.5.2',
                'ip': '4.4.4.1/24'
            }
        }
        r1 = self.addHost(name, cls=QuaggaRouter, quaggaConfFile=quaggaConf,
                          zebraConfFile=zebraConf, intfDict=intfs, greDict=greDict)

        # R2 router, AS65002 (intermediate)
        quaggaConf = '%sR2-quagga.conf' % CONFIG_DIR
        name = 'R2'
        # management interface (not used for now)
        eth0 = {
            'ipAddrs': ['192.168.102.1/30']
        }
        # internal interface (facing h2)
        eth1 = {
            'ipAddrs': ['20.0.0.1/8']
        }
        # external interface (facing R1)
        eth2 = {
            'ipAddrs': ['150.1.1.2/30']
        }
        # external interface (facing R3)
        eth3 = {
            'ipAddrs': ['150.1.2.1/30']
        }
        intfs = {
            '%s-eth0' % name: eth0,
            '%s-eth1' % name: eth1,
            '%s-eth2' % name: eth2,
            '%s-eth3' % name: eth3
        }
        greDict = None
        r2 = self.addHost(name, cls=QuaggaRouter, quaggaConfFile=quaggaConf,
                          zebraConfFile=zebraConf, intfDict=intfs, greDict=greDict)

        # R3 router, AS65003 (intermediate)
        quaggaConf = '%sR3-quagga.conf' % CONFIG_DIR
        name = 'R3'
        # management interface (not used for now)
        eth0 = {
            'ipAddrs': ['192.168.103.1/30']
        }
        # internal interface (facing h3)
        eth1 = {
            'ipAddrs': ['30.0.0.1/8']
        }
        # external interface (facing R2)
        eth2 = {
            'ipAddrs': ['150.1.2.2/30']
        }
        # external interface (facing R4)
        eth3 = {
            'ipAddrs': ['150.1.4.1/30']
        }
        # external interface (facing R5)
        eth4 = {
            'ipAddrs': ['150.1.5.1/30']
        }
        intfs = {
            '%s-eth0' % name: eth0,
            '%s-eth1' % name: eth1,
            '%s-eth2' % name: eth2,
            '%s-eth3' % name: eth3,
            '%s-eth4' % name: eth4
        }
        greDict = None
        r3 = self.addHost(name, cls=QuaggaRouter, quaggaConfFile=quaggaConf,
                          zebraConfFile=zebraConf, intfDict=intfs, greDict=greDict)

        # R4 router, AS65004 (hijacking AS)
        quaggaConf = '%sR4-quagga.conf' % CONFIG_DIR
        name = 'R4'
        # management interface (not used for now)
        eth0 = {
            'ipAddrs': ['192.168.104.1/30']
        }
        # internal interface (facing h4)
        eth1 = {
            'ipAddrs': ['10.0.0.1/8']
        }
        # external interface (facing R3)
        eth2 = {
            'ipAddrs': ['150.1.4.2/30']
        }
        intfs = {
            '%s-eth0' % name: eth0,
            '%s-eth1' % name: eth1,
            '%s-eth2' % name: eth2
        }
        greDict = None
        r4 = self.addHost(name, cls=QuaggaRouter, quaggaConfFile=quaggaConf,
                          zebraConfFile=zebraConf, intfDict=intfs, greDict=greDict)

        # R5 router, AS65005 (moas)
        quaggaConf = '%sR5-quagga.conf' % CONFIG_DIR
        name = 'R5'
        # management interface (not used for now)
        eth0 = {
            'ipAddrs': ['192.168.105.1/30']
        }
        # internal interface (facing h5 and exabgp rc 65005)
        eth1 = {
            'ipAddrs': ['50.0.0.1/8']
        }
        # external interface (facing R3)
        eth2 = {
            'ipAddrs': ['150.1.5.2/30']
        }
        # external interface (facing artemis, as router-attached MOAS agent)
        eth3 = {
            'ipAddrs': ['192.168.201.1/30']
        }
        intfs = {
            '%s-eth0' % name: eth0,
            '%s-eth1' % name: eth1,
            '%s-eth2' % name: eth2,
            '%s-eth3' % name: eth3
        }
        greDict = {
            'gre1': {
                'local': '150.1.5.2',
                'remote': '150.1.1.1',
                'ip': '4.4.4.2/24'
            }
        }
        r5 = self.addHost(name, cls=QuaggaRouter, quaggaConfFile=quaggaConf,
                          zebraConfFile=zebraConf, intfDict=intfs, greDict=greDict)

        # L2 switch, AS65001
        l2_sw_1 = self.addSwitch(
            'l2_sw_1', dpid='0000000000000001', failMode='standalone', cls=L2Switch)

        # l2 switch, AS65005
        l2_sw_5 = self.addSwitch(
            'l2_sw_5', dpid='0000000000000005', failMode='standalone', cls=L2Switch)

        # data plane host at AS65001
        h1 = self.addHost('h1', ip='10.0.0.100/8', defaultRoute='via 10.0.0.1')

        # data plane host at AS65002
        h2 = self.addHost('h2', ip='20.0.0.100/8', defaultRoute='via 20.0.0.1')

        # data plane host at AS65003
        h3 = self.addHost('h3', ip='30.0.0.100/8', defaultRoute='via 30.0.0.1')

        # data plane host at AS65004
        h4 = self.addHost('h4', ip='10.0.0.100/8', defaultRoute='via 10.0.0.1')

        # data plane host at AS65005
        h5 = self.addHost('h5', ip='50.0.0.100/8', defaultRoute='via 50.0.0.1')

        # set up the artemis host at AS65001
        name = 'artemis'
        # facing exabgp rc 65001
        eth0 = {
            'ipAddrs': ['192.168.1.2/24']
        }
        # facing exabgp rc 65005
        eth1 = {
            'ipAddrs': ['192.168.5.2/24']
        }
        # facing local router R1
        eth2 = {
            'ipAddrs': ['192.168.101.2/24']
        }
        # facing external MOAS agent
        eth3 = {
            'ipAddrs': ['192.168.201.2/24']
        }
        intfs = {
            '%s-eth0' % name: eth0,
            '%s-eth1' % name: eth1,
            '%s-eth2' % name: eth2,
            '%s-eth3' % name: eth3
        }
        artemis = self.addHost(
            name,
            inNamespace=False,
            cls=Artemis,
            intfDict=intfs)

        # set up the exaBGP monitor at AS65001
        name = 'exa65001'
        eth0 = {
            'ipAddrs': ['10.0.0.3/8']
        }
        eth1 = {
            'ipAddrs': ['192.168.1.1/24']
        }
        intfs = {
            '%s-eth0' % name: eth0,
            '%s-eth1' % name: eth1
        }
        exabgp_65001 = self.addHost(name, cls=ExaBGPRouter,
                                    exaBGPconf='%sexabgp-65001.conf' % CONFIG_DIR,
                                    intfDict=intfs)

        # set up the exaBGP monitor at AS65005
        name = 'exa65005'
        eth0 = {
            'ipAddrs': ['50.0.0.3/8']
        }
        eth1 = {
            'ipAddrs': ['192.168.5.1/24']
        }
        intfs = {
            '%s-eth0' % name: eth0,
            '%s-eth1' % name: eth1
        }
        exabgp_65005 = self.addHost(name, cls=ExaBGPRouter,
                                    exaBGPconf='%sexabgp-65005.conf' % CONFIG_DIR,
                                    intfDict=intfs)

        # set topology links

        # link R1-L2_SW_1: R1:eth1:10.0.0.1 - L2_SW_1:eth1
        self.addLink(r1, l2_sw_1, port1=1, port2=1)

        # link L2_SW_1-H1: L2_SW_1:eth2 - H1:eth0:10.0.0.100
        self.addLink(l2_sw_1, h1, port1=2, port2=0)

        # link L2_SW_1-exabgp_65001: L2_SW_1:eth3 - exabgp_65001:eth0:10.0.0.3
        self.addLink(l2_sw_1, exabgp_65001, port1=3, port2=0)

        # link exabgp_65001-artemis: exabgp_65001:eth1:192.168.1.1 -
        # artemis:eth0:192.168.1.2
        self.addLink(exabgp_65001, artemis, port1=1, port2=0)

        # link R1-artemis: R1:eth0:192.168.101.1 - artemis:eth2:192.168.101.2
        self.addLink(r1, artemis, port1=0, port2=2)

        # link R1-R2: R1:eth2:150.1.1.1 - R2:eth2:150.1.1.2
        self.addLink(r1, r2, port1=2, port2=2)

        # link R2-H2: R2:eth1:20.0.0.1 - H2:eth0:20.0.0.100
        self.addLink(r2, h2, port1=1, port2=0)

        # link R2-R3: R2:eth3:150.1.2.1 - R3:eth2:150.1.2.2
        self.addLink(r2, r3, port1=3, port2=2)

        # link R3-H3: R2:eth1:30.0.0.1 - H3:eth0:30.0.0.100
        self.addLink(r3, h3, port1=1, port2=0)

        # link R3-R4: R3:eth3:150.1.4.1 - R4:eth2:150.1.4.2
        self.addLink(r3, r4, port1=3, port2=2)

        # link R4-H4: R4:eth1:10.0.0.1 - H4:eth0:10.0.0.100
        self.addLink(r4, h4, port1=1, port2=0)

        # link R3-R5: R3:eth4:150.1.5.1 - R5:eth2:150.1.5.2
        self.addLink(r3, r5, port1=4, port2=2)

        # link R5-L2_SW_5: R5:eth1:50.0.0.1 - L2_SW_5:eth1
        self.addLink(r5, l2_sw_5, port1=1, port2=1)

        # link L2_SW_5-H5: L2_SW_5:eth2 - H5:eth0:50.0.0.100
        self.addLink(l2_sw_5, h5, port1=2, port2=0)

        # link L2_SW_5-exabgp_65005: L2_SW_1:eth3 - exabgp_65005:eth0:50.0.0.3
        self.addLink(l2_sw_5, exabgp_65005, port1=3, port2=0)

        # link exabgp_65005-artemis: exabgp_65005:eth1:192.168.5.1 -
        # artemis:eth1:192.168.5.2
        self.addLink(exabgp_65005, artemis, port1=1, port2=1)

        # link artemis-R5 (MOAS agent):
        # artemis:eth3:192.168.201.2-R5:eth3:192.168.201.1
        self.addLink(artemis, r5, port1=3, port2=3)


topos = {'artemis': ArtemisTopo}

if __name__ == '__main__':
    setLogLevel('debug')
    topo = ArtemisTopo()

    net = Mininet(topo=topo, build=False)
    net.build()
    net.start()

    CLI(net)

    net.stop()

    info("done\n")
