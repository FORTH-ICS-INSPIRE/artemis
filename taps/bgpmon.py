# import re
# import time
# import socket
# from xml.etree import ElementTree as ET
# from core.files import WriteLogs

# BUFF_SIZE = 4096
# RECONNECT_INTERVAL = 1

# class BGPmon:

#     bgpmon_conf = {'host_ip': None, 'host_port': None}
    
    
#     def __init__(self, prefixes_tree, raw_log_queue, adress_port):
#         self.prefix_tree = prefixes_tree
#         self.write2file = WriteLogs(service='RIPEris', monitor="BGPmon")
#         self.bgpmon_conf['host_ip'] = adress_port[0]
#         self.bgpmon_conf['host_ip'] = adress_port[1]
#         self.raw_log_queue = raw_log_queue
#         self.start()


#     def start(self):
#         print("[BGPMON] service enabled!")
#         s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Create a socket object
#         reconnect = True

#         while True:
#             try:
#                 s.connect((self.bgpmon_conf['host_ip'], self.bgpmon_conf['host_port']))

#                 # init received_data and bgp_msg strings
#                 bgp_xml = ""
#                 received_data = ""

#                 while True:
#                     received_data += str(s.recv(BUFF_SIZE).decode("utf-8"))
                    
#                     (received_data, bgp_data) = self.parse_bgp_xml(bgp_xml, received_data)

#                     # Check if prefix is in our monitor list
#                     for prefix in bgp_data[1]:
#                         if(self.check_prefix(prefix) is not None):

#                             bgp_message = {'timestamp': bgp_data[0], 
#                                             'prefix': bgp_data[1], 
#                                             'as_path': bgp_data[2],
#                                             'peer': bgp_data[3],
#                                             'type': bgp_data[4]}

#                             # Write raw log
#                             self.write2file.append_log(bgp_message)

#                             # Put in queue to be tranformed to Pformat
#                             self.raw_log_queue.put(('BGPmon', 'all', bgp_message))
            
#             except socket.error as msg:
#                 print('Could not connect to BGPmon server! Reconnecting in 1 sec...')
#                 reconnect = True
#                 time.sleep(RECONNECT_INTERVAL)

#             if not reconnect:
#                 break

#         s.close  # Close the socket when done



#     def parse_bgp_xml(self, bgp_msg, received_data):
#         timestamp = ""
#         prefixes = []
#         as_path = []
#         peer = ""
#         type_of_msg = ""

#         # Skip <xml> tag
#         if "<xml>" in received_data:
#             received_data = received_data[5:]

#         xml_msgs = re.findall(r'<BGP_MONITOR_MESSAGE.*?</BGP_MONITOR_MESSAGE>', received_data)

#         received_data = received_data.split("</BGP_MONITOR_MESSAGE>")[-1]


#         for xml in xml_msgs:
#             try:
#                 root = ET.fromstring(xml)

#                 # timestamp
#                 for child in root:
#                     if "OBSERVED_TIME" in child.tag:
#                         timestamp = child[0].text

#                 # as_path
#                 try:
#                     asns = root[6][1][0]
#                     for asn in asns:
#                         as_path.append(str(asn.text))
#                 except IndexError:
#                     pass

#                 # prefix
#                 try:
#                     update_tag = root[6]
#                     for child in update_tag:
#                         if "NLRI" in child.tag:
#                             prefixes.append(str(child.text))
#                 except IndexError:  # it is a withdraw message
#                     pass

#                 # peer/next_hop
#                 try:
#                     update_tag = root[6]
#                     for child in update_tag:
#                         if "NEXT_HOP" in child.tag:
#                             peer = child.text
#                 except IndexError:  # it is a withdraw message
#                     pass


#             except ET.ParseError:
#                 print("Bad xml node")
                

#         if(len(xml_msgs) > 0):
#             if(len(as_path) == 0):
#                 type_of_msg = "W"
#             else:
#                 type_of_msg = "A"

#         return received_data, (timestamp, prefixes, as_path, peer, type_of_msg)

#     def check_prefix(self, prefix):
#         try:
#             return self.prefix_tree.search_worst(prefix)
#         except:
#             return None
