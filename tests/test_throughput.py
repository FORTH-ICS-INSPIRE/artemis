import os
import sys

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)
os.environ['FLASK_CONFIGURATION'] = 'testing'

import unittest
import mock
import logging
from core.yamlparser import ConfigurationLoader
from core.detection import Detection
from webapp.webapp import WebApplication
from webapp import app
from webapp.data.models import db
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from webapp.data.models import Monitor


NUM_OF_ENTRIES = 100

mon_fields = {
        'id':0,
        'prefix':1,
        'origin_as':2,
        'peer_as':3,
        'as_path':4,
        'service':5,
        'type':6,
        'communities':7,
        'timestamp':8,
        'hijack_id':9,
        'handled':10
}

hij_fields = {
        'id':0,
        'type':1,
        'prefix':2,
        'hijack_as':3,
        'num_peers_seen':4,
        'num_asns_inf':5,
        'time_started':6,
        'time_last_updated':7
}


class TestDetection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        logging.disable(logging.INFO)
        try:
            cls.webapp = WebApplication()
            cls.webapp.start()
        except:
            pass


    @classmethod
    def tearDownClass(cls):
        cls.webapp.stop()
        os.remove(app.config['SQLALCHEMY_DATABASE_URI'][10:])
        logging.disable(logging.NOTSET)


    def setUp(self):
        self.detection = Detection(None)

        # prefix: 10.0.0.0/24, origin_asns = {1}, neighbors = {2,3,4}
        node = self.detection.prefix_tree.add('10.0.0.0/24')
        node.data['confs'] = []

        conf_obj = {'origin_asns': {1}, 'neighbors': {2,3,4}}
        node.data['confs'].append(conf_obj)

        with app.app_context():
            db.drop_all()
            db.create_all()

        self.conn = sqlite3.connect('/tmp/test.db')
        self.c = self.conn.cursor()

    def tearDown(self):
        pass

    @mock.patch.object(Detection, 'init_detection')
    def testThroughput(self, mock_detection):

        def pushMonitor(time):
            try:
                mon = Monitor({
                        'prefix':'10.0.0.0/25',
                        'service':'testing',
                        'type':'A',
                        'as_path': [ 9, 8, 7, 6, 5, 4, 1 ],
                        'timestamp': time
                })

                with app.app_context():
                    db.session.add(mon)
                    db.session.commit()
                    self.detection.monitor_queue.put(mon.id)
            except Exception as e:
                print(e)

        self.detection.start()

        with ThreadPoolExecutor(max_workers=10) as executor:
            [executor.submit(pushMonitor, time) for time in range(100)]

        while True:
            time.sleep(5)
            self.c.execute('SELECT * FROM monitors WHERE handled=1')
            if len(self.c.fetchall()) == 100:
                self.detection.stop()
                time.sleep(1)
                break


if __name__ == '__main__':
    unittest.main()
