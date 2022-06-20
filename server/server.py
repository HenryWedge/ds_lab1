# coding=utf-8
import argparse
import json
import sys
from threading import Lock, Thread
import time
import traceback
import bottle
from bottle import Bottle, request, template, run, static_file
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import requests
import json
import base64


# ------------------------------------------------------------------------------------------------------


class Blackboard():

    def __init__(self):
        self.content = dict()
        self.lock = Lock()  # use lock when you modify the content

    def get_content(self):
        with self.lock:
            cnt = self.content
        return cnt

    def modify_content(self, new_id, new_entry):
        with self.lock:
            self.content[str(new_id)] = new_entry
        return

    def delete_content(self, delete_id):
        with self.lock:
            self.content.pop(delete_id)
        return


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.id = int(ID)
        self.ip = str(IP)
        self.servers_list = servers_list

        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=512, backend=default_backend())
        self.public_key = self.private_key.public_key()
        self.server_id_public_key_dictionary = dict()

        time.sleep(3)
        self.pem = self.format_public_key()
        self.send_public_key()

        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board/propagate', callback=self.add_entry_with_propagation)
        self.post('/board', callback=self.add_entry)
        self.post('/board/<param>/propagate', callback=self.modify_entry_with_propagation)
        self.post('/board/<param>/', callback=self.modify_entry)
        self.post('/', callback=self.post_index)
        self.get('/templates/<filename:path>', callback=self.get_template)
        self.post('/pk/receive', callback=self.receive_public_key)

    def format_public_key(self):
        return base64.b64encode(self.public_key.public_bytes(encoding=serialization.Encoding.PEM,
                                                             format=serialization.PublicFormat.SubjectPublicKeyInfo))

    def send_public_key(self):
        print("start_send")
        self.propagate_to_all_servers('/pk/receive', self.to_json({"ip": self.ip, "public_key": "Bla"}), req='POST')

    def receive_public_key(self):
        print("receive_public_key")
        answer = self.from_json(request.forms)
        print(answer['ip'])
        self.server_id_public_key_dictionary[answer['ip']] = answer['public_key']

    def to_json(self, send_object):
        json_obj = dict()
        json_obj['data'] = json.dumps(send_object)
        return json_obj

    def from_json(self, forms):
        return json.loads(forms['data'])

    def sign(self, message):
        return self.private_key.sign(base64.b64encode(message.encode()),
                                     padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                 salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())

    def verify(self, public_key, message, signature):
        print(message)
        public_key = serialization.load_pem_public_key(base64.b64decode(public_key), backend=default_backend())
        try:
            public_key.verify(signature, base64.b64encode(message.encode()),
                              padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                          salt_length=padding.PSS.MAX_LENGTH),
                              hashes.SHA256())
        except InvalidSignature:
            return False
        return True

    def hash(self, string):
        digester = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digester.update(string.encode())
        return base64.b64encode(digester.finalize()).decode()

    def do_parallel_task(self, method, args=None):
        thread = Thread(target=method,
                        args=args)
        thread.daemon = True
        thread.start()

    def do_parallel_task_after_delay(self, delay, method, args=None):
        thread = Thread(target=self._wrapper_delay_and_execute,
                        args=(delay, method, args))
        thread.daemon = True
        thread.start()

    def _wrapper_delay_and_execute(self, delay, method, args):
        time.sleep(delay)  # in sec
        method(*args)

    def contact_another_server(self, srv_ip, URI, params_dict, req='POST'):
        success = False
        # print("Params dict: {}: ".format(params_dict))
        try:
            if 'POST' in req:
                res = requests.post('http://{}{}'.format(srv_ip, URI),
                                    data=params_dict, json=params_dict)
            elif 'GET' in req:
                res = requests.get('http://{}{}'.format(srv_ip, URI))
            # result can be accessed res.json()
            if res.status_code == 200:
                success = True
        except Exception as e:
            print("[ERROR] " + str(e))
        return success

    def propagate_to_all_servers(self, URI, params_dict, req='POST'):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip:  # don't propagate to yourself
                self.do_parallel_task(method=self.contact_another_server, args=(srv_ip, URI, params_dict, req))

    # route to ('/')
    def index(self):
        return template('server/templates/index.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=self.blackboard.get_content().items(),
                        members_name_string='Julius Rüder and Hendrik Reiter')

    # get on ('/board')
    def get_board(self):
        return template('server/templates/blackboard.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=self.blackboard.get_content().items())

    def add_entry(self):
        try:
            new_entry = request.forms.get('entry')
            self.blackboard.modify_content(new_entry, new_entry)
        except Exception as e:
            print("[ERROR] " + str(e))

    def add_entry_with_propagation(self):
        self.add_entry()
        self.propagate_to_all_servers('/board', request.forms.dict, req='POST')

    def modify_entry(self, param):
        entry = request.params.get('entry')
        isModify = request.params.get('delete') == '0'
        self.blackboard.delete_content(param)

        if (isModify):
            self.blackboard.modify_content(entry, entry)
        return

    def modify_entry_with_propagation(self, param):
        self.modify_entry(param)
        self.propagate_to_all_servers('/board/{}/'.format(param), request.forms.dict, req='POST')

    # post on ('/')
    def post_index(self):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            print("Received: {}".format(new_entry))
        except Exception as e:
            print("[ERROR] " + str(e))

    def get_template(self, filename):
        return static_file(filename, root='./server/templates/')


# ------------------------------------------------------------------------------------------------------
def main():
    PORT = 80
    parser = argparse.ArgumentParser(description='Your own implementation of the distributed blackboard')
    parser.add_argument('--id',
                        nargs='?',
                        dest='id',
                        default=1,
                        type=int,
                        help='This server ID')
    parser.add_argument('--servers',
                        nargs='?',
                        dest='srv_list',
                        default="10.1.0.1,10.1.0.2",
                        help='List of all servers present in the network')
    args = parser.parse_args()
    server_id = args.id
    server_ip = "10.1.0.{}".format(server_id)
    servers_list = args.srv_list.split(",")

    try:
        application = Server(server_id,
                             server_ip,
                             servers_list)
        bottle.run(app=application,
                   server='paste',
                   host=server_ip,
                   port=PORT)
    except Exception as e:
        print("[ERROR] " + str(e))


# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
