import sys
import json
from urllib.request import urlopen
from bs4 import BeautifulSoup

collectors_obj = dict()

def parse_routeviews():
    html = urlopen("http://www.routeviews.org/routeviews/index.php/collectors/")
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all('tr')
    
    for row in rows:
        cells = row.find_all("td")
        if(len(cells) == 5):
            name = cells[0].text.replace('\n','').split('.routeviews')[0]
            MFG = cells[1].text
            BGP_proto = cells[2].text
            location = cells[4].text

            if('route-' in name):
                collectors_obj[name] = dict()
                collectors_obj[name]['MFG'] = MFG
                collectors_obj[name]['BGP_proto'] = BGP_proto
                collectors_obj[name]['location'] = location


def parse_ripe_ris():
    html = urlopen("https://www.ripe.net/analyse/internet-measurements/routing-information-service-ris/ris-raw-data")
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all('li')
    rrcs_obj = dict()

    for row in rows:
        text = row.text.lstrip()
        if '.ripe.net' in text:
            name = text.split('.')[0]
            collectors_obj[name] = dict()
            collectors_obj[name]['info'] = text.split('ripe.net')[1].lstrip().rstrip('\n')


def main():
    parse_routeviews()
    parse_ripe_ris()

    with open('collectors_info.json', 'w') as outfile:
        json.dump(collectors_obj, outfile)


main()