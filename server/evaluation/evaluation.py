import requests
from threading import Thread

srv_ip  = '10.1.0.1:80'
URI     = '/board/propagate'

def add_value(server_no, payload):
	requests.post('http://10.1.0.{}:80{}'.format(server_no + 1, '/board/propagate'),data={'entry':str(payload)})

def modify_value(server_no, payload):
	requests.post('http://10.1.0.{}:80{}'.format(server_no + 1, '/board/entry0/propagate'),data={'entry': payload, 'delete':0})

def add_scenario():
	for i in range(5):
		for server_no in range(8):
			Thread(target=add_value, args=(server_no, 'entry{}'.format(i))).start()


def modify_scenario():
	for server_no in range(8):
		Thread(target=modify_value, args=(server_no, 'modified entry {}'.format(server_no))).start()

modify_scenario()
