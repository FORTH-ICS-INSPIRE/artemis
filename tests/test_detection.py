
import os
import sys

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)
os.environ['FLASK_CONFIGURATION'] = 'testing'

import unittest
import mock
from core.parser import ConfParser
from core.detection import Detection
from webapp.webapp import WebApplication
from webapp import app
from webapp.data.models import db
import sqlite3

mon_fields = {
        'id':0,
        'prefix':1,
        'origin_as':2,
        'peer_as':3,
        'as_path':4,
        'service':5,
        'type':6,
        'timestamp':7,
        'hijack_id':8,
        'handled':9
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

def commit(entries):
    with app.app_context():
        for entry in entries:
            db.session.add(entry)
        db.session.commit()

class TestDetection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.webapp = WebApplication()
        cls.webapp.start()


    def setUp(self):
        self.detection = Detection(None)

        # prefix: 10.0.0.0/24, origin_asns = {1}, neighbors = {2,3,4}
        node = self.detection.prefix_tree.add('10.0.0.0/24')
        node.data['origin_asns'] = set([1])
        node.data['neighbors'] = set([2,3,4])

        with app.app_context():
            db.drop_all()
            db.create_all()

        self.conn = sqlite3.connect('/tmp/test.db')
        self.c = self.conn.cursor()


    def test_wrong_inputs(self):
        from webapp.data.models import Monitor
        self.assertRaises(KeyError, Monitor, {})
        msg = {
                'prefix':'10.0.0.0/24',
                'service':'testing',
                'type':'A',
                'as_path': [ '9 3 2 1', 8, 7, 6, 5, 4, 1 ],
                'timestamp': 0
        }
        self.assertRaises(ValueError, Monitor, msg)


    @mock.patch.object(Detection, 'init_detection')
    def test_type01_detection(self, mock_init):
        from webapp.data.models import Monitor

        # legitimate announce
        mon_1 = Monitor({
                'prefix':'10.0.0.0/24',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 4, 1 ],
                'timestamp': 0
        })

        # exact prefix type 0 hijack
        mon_2 = Monitor({
                'prefix':'10.0.0.0/24',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 4, 666 ],
                'timestamp': 1
        })

        # exact prefix type 1 hijack
        mon_3 = Monitor({
                'prefix':'10.0.0.0/24',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 666, 1 ],
                'timestamp': 2
        })

        commit([mon_1, mon_2, mon_3])
        self.detection.parse_queue()

        # query sqlite db
        self.c.execute('SELECT * FROM monitors')
        monitor_rows = self.c.fetchall()
        self.c.execute('SELECT * FROM hijacks')
        hijack_rows = self.c.fetchall()

        # check if number of entries are correct
        self.assertEqual(len(monitor_rows), 3, msg='[!] Wrong number of monitor entries')
        self.assertEqual(len(hijack_rows), 2, msg='[!] Wrong number of detected hijacks')

        # check types
        self.assertEqual(hijack_rows[0][hij_fields['type']], '0', msg='[!] Wrong hijack type detected')
        self.assertEqual(hijack_rows[1][hij_fields['type']], '1', msg='[!] Wrong hijack type detected')

        # check monitors updated hijack id
        self.assertEqual(monitor_rows[0][mon_fields['hijack_id']], None, msg='[!] Legal Monitor entry has Hijack ID set')
        self.assertEqual(monitor_rows[1][mon_fields['hijack_id']], hijack_rows[0][hij_fields['id']], msg='[!] Malicious Monitor entry has no Hijack ID')
        self.assertEqual(monitor_rows[2][mon_fields['hijack_id']], hijack_rows[1][hij_fields['id']], msg='[!] Malicious Monitor entry has no Hijack ID')

        # check if monitors are handled
        for monitor_entry in monitor_rows:
            self.assertTrue(monitor_entry[-1], msg='[!] The monitor should have been handled')


        # testing different as_path for same hijack and newer timestamp
        mon_4 = Monitor({
                'prefix':'10.0.0.0/24',
                'service':'testing',
                'type':'A',
                'as_path': [ 10, 20, 30, 40, 50, 60, 666 ],
                'timestamp': 666
        })

        commit([mon_4])
        self.detection.parse_queue()

        self.c.execute('SELECT * FROM monitors')
        monitor_rows = self.c.fetchall()
        self.c.execute('SELECT * FROM hijacks')
        hijack_rows = self.c.fetchall()

        self.assertEqual(len(monitor_rows), 4, msg='[!] Wrong number of monitor entries')
        self.assertEqual(len(hijack_rows), 2, msg='[!] Wrong number of hijacks detected')

        self.assertEqual(hijack_rows[0][hij_fields['time_last_updated']], 666, msg='[!] Hijack timstamp not updated')
        self.assertEqual(hijack_rows[0][hij_fields['num_asns_inf']], 12, msg='[!] Wrong number of infected ASNs')

        # testing num_asns_inf with path prepending and smaller timestamp
        mon_5 = Monitor({
                'prefix':'10.0.0.0/24',
                'service':'testing',
                'type':'A',
                'as_path': [ 10, 10, 10, 10, 10, 666 ],
                'timestamp': 300
        })

        commit([mon_5])
        self.detection.parse_queue()

        # query sqlite db
        self.c.execute('SELECT * FROM monitors')
        monitor_rows = self.c.fetchall()
        self.c.execute('SELECT * FROM hijacks')
        hijack_rows = self.c.fetchall()

        self.assertEqual(len(monitor_rows), 5, msg='[!] Wrong number of monitor entries')
        self.assertEqual(len(hijack_rows), 2, msg='[!] Wrong number of hijacks detected')

        self.assertEqual(hijack_rows[0][hij_fields['time_last_updated']], 666, msg='[!] Hijack timstamp not updated')
        self.assertEqual(hijack_rows[0][hij_fields['num_asns_inf']], 12, msg='[!] Wrong number of infected ASNs')


    @mock.patch.object(Detection, 'init_detection')
    def test_prepending_check(self, mock_init):
        from webapp.data.models import Monitor

        # legitimate update with path prepending
        mon_1 = Monitor({
                'prefix':'10.0.0.0/24',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 4, 4, 1, 1, 1 ],
                'timestamp': 0
        })

        # routing loop inside as path
        mon_2 = Monitor({
                'prefix':'10.0.0.0/24',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 7, 6, 4, 1 ],
                'timestamp': 0
        })

        commit([mon_1, mon_2])
        self.detection.parse_queue()

        # query sqlite db
        self.c.execute('SELECT * FROM monitors')
        monitor_rows = self.c.fetchall()
        self.c.execute('SELECT * FROM hijacks')
        hijack_rows = self.c.fetchall()

        # check if number of entries are correct
        self.assertEqual(len(monitor_rows), 2, msg='[!] Wrong number of monitor entries')
        self.assertEqual(len(hijack_rows), 0, msg='[!] Wrong number of detected hijacks')


    @mock.patch.object(Detection, 'init_detection')
    def test_subprefix_type01_detection(self, mock_init):
        from webapp.data.models import Monitor

        # type 0 subprefix hijack
        mon_1 = Monitor({
                'prefix':'10.0.0.0/25',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 4, 666 ],
                'timestamp': 1
        })

        # type 0 subprefix hijack
        mon_2 = Monitor({
                'prefix':'10.0.0.128/25',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 4, 777 ],
                'timestamp': 2
        })

        commit([mon_1, mon_2])
        self.detection.parse_queue()

        # query sqlite db
        self.c.execute('SELECT * FROM monitors')
        monitor_rows = self.c.fetchall()
        self.c.execute('SELECT * FROM hijacks')
        hijack_rows = self.c.fetchall()

        # check if number of entries are correct
        self.assertEqual(len(monitor_rows), 2, msg='[!] Wrong number of monitor entries')
        self.assertEqual(len(hijack_rows), 2, msg='[!] Wrong number of detected hijacks')

        # check types
        self.assertEqual(hijack_rows[0][hij_fields['type']], '0', msg='[!] Wrong hijack type detected')
        self.assertEqual(hijack_rows[1][hij_fields['type']], '0', msg='[!] Wrong hijack type detected')

        # check monitors updated hijack id
        self.assertEqual(monitor_rows[0][mon_fields['hijack_id']], hijack_rows[0][hij_fields['id']], msg='[!] Malicious Monitor entry has no Hijack ID')
        self.assertEqual(monitor_rows[1][mon_fields['hijack_id']], hijack_rows[1][hij_fields['id']], msg='[!] Malicious Monitor entry has no Hijack ID')

        # check if monitors are handled
        for monitor_entry in monitor_rows:
            self.assertTrue(monitor_entry[-1], msg='[!] The monitor should have been handled')

        # update previous hijack
        mon_3 = Monitor({
                'prefix':'10.0.0.0/25',
                'service':'testing',
                'type':'A',
                'as_path': [ 10, 20, 30, 40, 50, 60, 666 ],
                'timestamp': 666
        })

        commit([mon_3])
        self.detection.parse_queue()

        # query sqlite db
        self.c.execute('SELECT * FROM monitors')
        monitor_rows = self.c.fetchall()
        self.c.execute('SELECT * FROM hijacks')
        hijack_rows = self.c.fetchall()

        # check if number of entries are correct
        self.assertEqual(len(monitor_rows), 3, msg='[!] Wrong number of monitor entries')
        self.assertEqual(len(hijack_rows), 2, msg='[!] Wrong number of hijacks detected')

        # check if hijack fields are updated correctly
        self.assertEqual(hijack_rows[0][hij_fields['time_last_updated']], 666, msg='[!] Hijack timstamp not updated')
        self.assertEqual(hijack_rows[0][hij_fields['num_asns_inf']], 12, msg='[!] Wrong number of infected ASNs')

        # new hijack entry with different originator
        mon_4 = Monitor({
                'prefix':'10.0.0.0/25',
                'service':'testing',
                'type':'A',
                'as_path': [ 10, 10, 10, 10, 10, 777 ],
                'timestamp': 300
        })

        commit([mon_4])
        self.detection.parse_queue()

        # query sqlite db
        self.c.execute('SELECT * FROM monitors')
        monitor_rows = self.c.fetchall()
        self.c.execute('SELECT * FROM hijacks')
        hijack_rows = self.c.fetchall()

        # check if number of entries are correct
        self.assertEqual(len(monitor_rows), 4, msg='[!] Wrong number of monitor entries')
        self.assertEqual(len(hijack_rows), 3, msg='[!] Wrong number of hijacks detected')

        # check if hijack fields are updated correctly
        self.assertEqual(hijack_rows[2][hij_fields['time_last_updated']], 300, msg='[!] Hijack timstamp not updated')
        self.assertEqual(hijack_rows[2][hij_fields['num_asns_inf']], 1, msg='[!] Wrong number of infected ASNs')


    @mock.patch.object(Detection, 'init_detection')
    def test_superprefix(self, mock_init):
        from webapp.data.models import Monitor

        # superprefix announce
        mon_1 = Monitor({
                'prefix':'10.0.0.0/23',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 4, 666 ],
                'timestamp': 1
        })

        # superprefix announce
        mon_2 = Monitor({
                'prefix':'10.0.0.0/20',
                'service':'testing',
                'type':'A',
                'as_path': [ 9, 8, 7, 6, 5, 4, 777 ],
                'timestamp': 2
        })

        commit([mon_1, mon_2])
        self.detection.parse_queue()

        # query sqlite db
        self.c.execute('SELECT * FROM monitors')
        monitor_rows = self.c.fetchall()
        self.c.execute('SELECT * FROM hijacks')
        hijack_rows = self.c.fetchall()

        # check if number of entries are correct
        self.assertEqual(len(monitor_rows), 2, msg='[!] Wrong number of monitor entries')
        self.assertEqual(len(hijack_rows), 0, msg='[!] Wrong number of detected hijacks')


    @classmethod
    def tearDownClass(cls):
        cls.webapp.stop()
        os.remove(app.config['SQLALCHEMY_DATABASE_URI'][10:])


if __name__ == '__main__':
    unittest.main()
