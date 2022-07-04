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
quite_mode = True


def to_json(send_object):
    json_obj = dict()
    if hasattr(send_object, 'to_string'):
        json_obj['data'] = send_object.to_string()
    else:
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
    public_key = serialization.load_pem_public_key(base64.b64decode(public_key), backend=default_backend())
    try:
        public_key.verify(base64.b64decode(signature), base64.b64encode(message.encode()),
                          padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                      salt_length=padding.PSS.MAX_LENGTH),
                          hashes.SHA256())
    except InvalidSignature:
        return False
    print("Successfully verified")
    return True


def hash_string(string):
    digester = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digester.update(string.encode())
    return base64.b64encode(digester.finalize()).decode()


class Transaction():
    def __init__(self, diploma, public_key_1, signature_1, public_key_2, signature_2):
        self.diploma = diploma
        self.public_key_1 = public_key_1
        self.public_key_2 = public_key_2
        self.signature_1 = signature_1
        self.signature_2 = signature_2

    def to_string(self):
        return json.dumps(self, default=lambda x: x.__dict__, indent=4)

    def is_valid(self):
        print("publicKey: {} \n signature: {}".format(self.public_key_1, self.signature_1))
        print("publicKey: {} \n signature: {}".format(self.public_key_2, self.signature_2))

        return verify(self.public_key_1, self.diploma.to_string(), self.signature_1) \
               and verify(self.public_key_2, self.diploma.to_string(), self.signature_2)

    @classmethod
    def from_dict(cls, dict):
        return Transaction(Diploma.from_dict(dict['diploma']), dict['public_key_1'], dict['signature_1'],
                           dict['public_key_2'], dict['signature_2'])


class Block():
    def __init__(self, previous_block_hash):
        self.previous_block_hash = previous_block_hash
        self.transactions = []
        self.nonce = 0

    def add_transaction(self, transaction):
        self.transactions.append(transaction)

    def to_string(self):
        return json.dumps(self, default=lambda x: x.__dict__, indent=4)

    def is_valid(self):
        block_hash = hash_string(self.to_string())

        if not quite_mode:
            print("BlockHash: {}".format(block_hash))
        return block_hash[0] == str(0)  # and block_hash[1] == str(0)

    def hash_block_with_nonce(self, nonce):
        self.nonce = nonce
        if not quite_mode:
            print("TRY with nonce: {}".format(nonce))
        return self.is_valid()


class Diploma():
    def __init__(self, name, subject, grade):
        self.name = name
        self.subject = subject
        self.grade = grade

    def to_string(self):
        return json.dumps(self, default=lambda x: x.__dict__, indent=4)

    @classmethod
    def from_dict(self, dict):
        return Diploma(dict['name'], dict['subject'], dict['grade'])


class SignRequest():
    def __init__(self, signature, diploma, public_key):
        self.signature = signature
        self.diploma = diploma
        self.public_key = public_key


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
        self.sign_request_dict = dict()
        self.last_block = Block(0)

        time.sleep(3)
        self.pem = format_public_key(self.public_key)
        self.send_public_key()

        self.do_parallel_task(method=self.create_new_block, args=())

        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board/propagate', callback=self.add_entry_with_propagation)
        self.post('/', callback=self.post_index)
        self.get('/templates/<filename:path>', callback=self.get_template)
        self.post('/pk/receive', callback=self.receive_public_key)
        self.post('/block/new', callback=self.receive_block)
        self.post('/transaction/new', callback=self.receive_transaction)
        self.post('/signrequest/new', callback=self.create_sign_request)
        self.post('/signrequest/receive', callback=self.receive_sign_request)
        self.post('/signrequest/answer/<param>', callback=self.answer_sign_request)

    def create_sign_request(self):
        entry_name = request.forms.get('name')
        entry_subject = request.forms.get('subject')
        entry_grade = request.forms.get('grade')
        entry_target = request.forms.get('target')

        sign_request = Diploma(entry_name, entry_subject, entry_grade)
        signature = sign(self.private_key, sign_request.to_string())
        json = to_json(sign_request)
        json['signature'] = signature
        json['public_key'] = format_public_key(self.public_key)
        self.contact_another_server("10.1.0.{}".format(entry_target), "/signrequest/receive", json)

    def receive_sign_request(self):
        signature = request.forms['signature']
        public_key = request.forms['public_key']
        diploma = Diploma.from_dict(from_json(request.forms))
        # hash_string(sign_request.to_string())
        self.sign_request_dict[str(random.randint(0, 9999))] = SignRequest(signature, diploma, public_key)

    def answer_sign_request(self, param):
        sign_request = self.sign_request_dict[param]
        accept = request.params.get('accept') == '1'

        print("accept: {}".format(accept), "sign_request_id: {}".format(param))

        if accept:
            self.add_entry_with_propagation(sign_request)

        self.sign_request_dict.pop(param)

    def receive_block(self):
        new_block = from_json(request.forms)

        for transaction in new_block['transactions']:
            transaction = Transaction.from_dict(transaction)
            if not transaction.is_valid():
                print("!!!!!!!!!!!!!! \n Received invalid transaction \n \n")
            self.blackboard.modify_content(hash_string(transaction.to_string()), transaction.diploma)

        print("Validity of block was checked! It will be added to the block chain!")

        nb = Block(new_block['previous_block_hash'])
        nb.transactions = [Transaction.from_dict(tx) for tx in new_block['transactions']]
        nb.nonce = new_block['nonce']

        print(nb.to_string())

        previous_block_hash = hash_string(nb.to_string())
        self.last_block = Block(previous_block_hash)

    def receive_transaction(self):
        self.last_block.transactions.append(Transaction.from_dict(from_json(request.forms)))

    def create_new_block(self):
        print("Start mining")
        finished = False

        while not finished:
            while not self.last_block.transactions:
                time.sleep(1)
            time.sleep(0.5)
            nonce = random.randint(0, 999999)
            finished = self.last_block.hash_block_with_nonce(nonce)

        for transaction in self.last_block.transactions:
            self.blackboard.modify_content(hash_string(transaction.to_string()), transaction.diploma)

        self.propagate_to_all_servers('/block/new', to_json(self.last_block), req='POST')

        print("---------")
        print("Last Block:")
        print(self.last_block.to_string())
        print("---------")
        self.last_block.previous_block_hash = hash_string(self.last_block.to_string())
        self.last_block = Block(self.last_block.previous_block_hash)

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
        board_dict = dict()
        board_dict['data'] = self.blackboard.get_content().items()
        board_dict['accept'] = self.sign_request_dict.items()
        return template('server/templates/index.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=board_dict,
                        members_name_string='Julius Rüder and Hendrik Reiter')

    # get on ('/board')
    def get_board(self):
        board_dict = dict()
        board_dict['data'] = self.blackboard.get_content().items()
        board_dict['accept'] = self.sign_request_dict.items()
        return template('server/templates/blackboard.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=board_dict)

    def add_entry_with_propagation(self, sign_request):
        print("!!!!!!!!!\n A: {} \n B: {} \n !!!!!!!!!!".format(format_public_key(self.public_key),
                                                                sign_request.public_key))

        tx = Transaction(sign_request.diploma,
                         format_public_key(self.public_key), sign(self.private_key, sign_request.diploma.to_string()),
                         sign_request.public_key, sign_request.signature)
        self.last_block.add_transaction(tx)
        self.blackboard.modify_content(hash_string(tx.to_string()), sign_request.diploma)

        self.propagate_to_all_servers('/transaction/new', to_json(tx), req='POST')

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
