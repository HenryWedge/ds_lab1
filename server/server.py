# coding=utf-8
import argparse
import random
import string
from threading import Lock, Thread
import time
import bottle
from bottle import Bottle, request, template, static_file
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
def to_json(send_object):
    json_obj = dict()
    json_obj['data'] = json.dumps(send_object)
    return json_obj


def from_json(forms):
    return json.loads(forms['data'])


def format_public_key(public_key):
    return base64.b64encode(public_key.public_bytes(encoding=serialization.Encoding.PEM,
                                                    format=serialization.PublicFormat.SubjectPublicKeyInfo)).decode()


def sign(private_key, message: string):
    return base64.b64encode(private_key.sign(base64.b64encode(message.encode()),
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                        salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())).decode()


def verify(public_key, message, signature):
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


def hash_string(string):
    digester = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digester.update(string.encode())
    return base64.b64encode(digester.finalize()).decode()


class Transaction():
    def __init__(self, diploma, issuer_party_public_key, signature):
        self.diploma = diploma
        self.issuer_party_public_key = issuer_party_public_key
        self.signature = signature

    def to_string(self):
        return json.dumps(self, default=lambda x: x.__dict__,indent=4)




class Block():
    def __init__(self, previous_block_hash):
        self.previous_block_hash = previous_block_hash
        self.transactions = []
        #self.transactions.append(Transaction(Diploma('Alfred','IT','5'), "A", "A"))
        #self.transactions.append(Transaction(Diploma('Klaus','IT','5'), "B", "B"))
        self.nonce = 0

    def add_transaction(self,transaction):
        self.transactions.append(transaction)

    def to_string(self):
        #self.transactions.to_string()
        return json.dumps(self, default=lambda x: x.__dict__,indent=4)

    def is_valid(self):
        block_hash = hash_string(self.to_string())

        #########print("BlockHash: {}".format(block_hash))
        return block_hash[0] == str(0) #and block_hash[1] == str(0)

    def hash_block_with_nonce(self, nonce):
        self.nonce = nonce
        #########print("TRY with nonce: {}".format(nonce))
        return self.is_valid()


class Diploma():
    def __init__(self, name, subject, grade):
        self.name = name
        self.subject = subject
        self.grade = grade

    def to_string(self):
        return json.dumps(self, default=lambda x: x.__dict__,indent=4)


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
        self.last_block = Block(0)

        time.sleep(3)
        self.pem = format_public_key(self.public_key)
        self.send_public_key()

        self.do_parallel_task(method=self.create_new_block, args=())

        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board/propagate', callback=self.add_entry_with_propagation)
        self.post('/board', callback=self.add_entry)
        self.post('/board/<param>/propagate', callback=self.modify_entry_with_propagation)
        self.post('/board/<param>/', callback=self.modify_entry)
        self.post('/', callback=self.post_index)
        self.get('/templates/<filename:path>', callback=self.get_template)
        self.post('/pk/receive', callback=self.receive_public_key)
        self.post('/block/new', callback=self.receive_block)

    def receive_block(self):
        new_block = from_json(request.forms)
        for transaction in new_block['transactions']:
            self.blackboard.modify_content(transaction.tx_id, transaction.diploma)

    def create_new_block(self):
        print("Start mining")
        finished = False
        while not finished:
            time.sleep(0.1)
            nonce = random.randint(0, 999999)
            finished = self.last_block.hash_block_with_nonce(nonce)

        self.last_block.previous_block_hash = hash_string(self.last_block.to_string())
        print("---------")
        print("Last Block:")
        print(self.last_block.to_string())
        print("---------")
        self.create_new_block()

    def send_public_key(self):
        print("start_send")
        self.propagate_to_all_servers('/pk/receive', to_json({"ip": self.ip, "public_key": "Bla"}), req='POST')

    def receive_public_key(self):
        print("receive_public_key")
        answer = from_json(request.forms)
        print(answer['ip'])
        self.server_id_public_key_dictionary[answer['ip']] = answer['public_key']

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
            entry_name = request.forms.get('name')
            entry_subject = request.forms.get('subject')
            entry_grade = request.forms.get('grade')
            self.blackboard.modify_content(random.randint(0, 9999), Diploma(entry_name, entry_subject, entry_grade))
        except Exception as e:
            print("[ERROR] " + str(e))

    def add_entry_with_propagation(self):
        entry_name = request.forms.get('name')
        entry_subject = request.forms.get('subject')
        entry_grade = request.forms.get('grade')
        diploma = Diploma(entry_name, entry_subject, entry_grade)

        self.last_block.add_transaction(
            Transaction(diploma,
                        format_public_key(self.public_key), sign(self.private_key, diploma.to_string())))

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
