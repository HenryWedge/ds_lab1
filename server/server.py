# coding=utf-8
import argparse
import json
import sys
from threading import Lock, Thread
import time
import traceback
import bottle
from bottle import Bottle, request, template, run, static_file
import requests
import random
# ------------------------------------------------------------------------------------------------------

class Blackboard():

    def __init__(self):
        self.content = dict()
        self.lock = Lock() # use lock when you modify the content

    def get_content(self):
        with self.lock:
            cnt = self.content
        return cnt

    def set_content(self,cnt):
        with self.lock:
            self.content = cnt

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
        self.election = Election(self, IP, ID, servers_list)
        self.id = int(ID)
        self.ip = str(IP)
        self.servers_list = servers_list
        # list all REST URIs
        # if you add new URIs to the server, you need to add them here
        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board/propagate', callback=self.add_entry_with_propagation)
        self.post('/board', callback=self.add_entry)
        self.post('/board/<param>/propagate', callback=self.modify_entry_with_propagation)
        self.post('/board/<param>/', callback=self.modify_entry)
        self.post('/', callback=self.post_index)
        # we give access to the templates elements
        self.get('/templates/<filename:path>', callback=self.get_template)
        # You can have variables in the URI, here's an example
        # self.post('/board/<element_id:int>/', callback=self.post_board) where post_board takes an argument (integer) called element_id

        #-------------------------------------------------
        #Election
        self.post('/election/election', callback=self.election.answer)
        self.post('/election/answer', callback=self.election.recv_answer)
        self.post('/election/coordinator', callback=self.election.recv_coordinator)
        self.get('/testelection', callback=self.election.start_election)
        #-------------------------------------------------
        #Centralized Blackboard
        self.post('/board/update/recv', callback=self.recv_update_board)
        self.post('/coordinator/add', callback=self.coordinator_add)
        self.post('/coordinator/modify/<param>/', callback=self.coordinator_modify)

        # 2 add modify : board -> 1(C) board ->  2,3
        self.coordinator = None
        self.do_parallel_task_after_delay(2, self.election.start_election, args=())

    def set_coordinator(self, c):
        self.coordinator = c

    def do_parallel_task(self, method, args=None):
        # create a thread running a new task
        # Usage example: self.do_parallel_task(self.contact_another_server, args=("10.1.0.2", "/index", "POST", params_dict))
        # this would start a thread sending a post request to server 10.1.0.2 with URI /index and with params params_dict
        thread = Thread(target=method,
                        args=args)
        thread.daemon = True
        thread.start()

    def do_parallel_task_after_delay(self, delay, method, args=None):
        # create a thread, and run a task after a specified delay
        # Usage example: self.do_parallel_task_after_delay(10, self.start_election, args=(,))
        # this would start a thread starting an election after 10 seconds
        thread = Thread(target=self._wrapper_delay_and_execute,
                        args=(delay, method, args))
        thread.daemon = True
        thread.start()

    def _wrapper_delay_and_execute(self, delay, method, args):
        time.sleep(delay) # in sec
        method(*args)

    def contact_another_server(self, srv_ip, URI, req='POST', params_dict=None):
        # Try to contact another serverthrough a POST or GET
        # usage: server.contact_another_server("10.1.1.1", "/index", "POST", params_dict)
        success = False
        try:
            if 'POST' in req:
                res = requests.post('http://{}{}'.format(srv_ip, URI),
                                    data=params_dict)
            elif 'GET' in req:
                res = requests.get('http://{}{}'.format(srv_ip, URI))
            if res.status_code == 200:
                success = True
        except Exception as e:
            print("[ERROR] "+str(e))
        return success

    def propagate_to_all_servers(self, URI, req='POST', params_dict=None):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip: # don't propagate to yourself
                self.do_parallel_task(method=self.contact_another_server,args=(srv_ip, URI, req, params_dict))

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
            print("[ERROR] "+str(e))

    def add_entry_with_propagation(self):
        self.propagation_with_failure('/coordinator/add')

    def modify_entry(self, param):
        entry = request.params.get('entry')
        is_modify = request.params.get('delete') == '0'
        self.blackboard.delete_content(param)
        if is_modify:
            self.blackboard.modify_content(entry, entry)

    def propagation_with_failure(self, uri: str):
        forms = request.forms.dict
        success = self.contact_another_server(self.coordinator, uri, req='POST', params_dict=forms)
        if not success:
            self.coordinator = None
            self.do_parallel_task(self.election.start_election, args=())
            while self.coordinator==None:
                time.sleep(1)
            success = self.contact_another_server(self.coordinator, uri, req='POST', params_dict=forms)
            if not success:
                self.propagation_with_failure(uri)


    def modify_entry_with_propagation(self, param):
        self.propagation_with_failure('/coordinator/modify/{}/'.format(param))

    def update_board(self):
        self.propagate_to_all_servers(URI='/board/update/recv', req='POST', params_dict=self.blackboard.get_content())
    #post on '/board/update/recv'
    def recv_update_board(self):
        b = request.forms.dict
        b = {k: b[k][0] for k in b}
        self.blackboard.set_content(b)

    #post on '/coordinator/add',
    def coordinator_add(self):
        self.add_entry()
        self.update_board()
    #post on '/coordinator/modify/<param>/',
    def coordinator_modify(self, param):
        self.modify_entry(param)
        self.update_board()

    # post on ('/')
    def post_index(self):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            print("Received: {}".format(new_entry))
        except Exception as e:
            print("[ERROR] "+str(e))


    def get_template(self, filename):
        return static_file(filename, root='./server/templates/')

# ------------------------------------------------------------------------------------------------------


class Election():
    def __init__(self, server, server_ip, server_id, server_list):
        self.election_timer = 0
        self.server = server
        self.server_ip = server_ip
        self.server_list = server_list
        self.server_id = server_id
        self.coordinator_attribute = random.randint(0, 20)
        self.server_Dict = dict()

        self.current_coordinator = None
        self.got_answer = False

        self.lock = Lock()
        self.coordinator_counter = 0


    def start_election(self):
        time.sleep(0.1)
        self.server.do_parallel_task(method=self.election, args=())

    def election(self):
        if self.election_timer == 0:
            self.election_timer = time.time()

        data = {'server_ip': self.server_ip, 'coordinator_attribute': self.coordinator_attribute, 'server_id': self.server_id}

        with self.lock:
            self.coordinator_counter += 1

        for server in self.server_list:
            if server in self.server_Dict:
                if self.server_Dict[server] >= self.coordinator_attribute:
                    time.sleep(0.175)
                    self.server.do_parallel_task(method=self.server.contact_another_server, args=(server, '/election/election', 'POST', data))
            elif not(server == self.server_ip):
                time.sleep(0.175)
                self.server.do_parallel_task(method=self.server.contact_another_server, args=(server, '/election/election', 'POST', data))

        with self.lock:
            self.coordinator_counter += 1
            counter = self.coordinator_counter
        time.sleep(2)
        with self.lock:
            if not self.got_answer and counter == self.coordinator_counter:
                self.coordinator_counter += 1
                self.server.do_parallel_task(method=self.coordinator, args=())

    #post on '/election/election'
    def answer(self):
        ip = request.forms.get('server_ip')
        attribute = request.forms.get('coordinator_attribute')
        id = request.forms.get('server_id')
        data = {'take-over': self.server_ip}

        with self.lock:
            self.coordinator_counter += 1

        self.server_Dict[ip] = int(attribute)
        if int(attribute) < self.coordinator_attribute or (int(attribute) == self.coordinator_attribute and int(id) < self.server_id):
            time.sleep(0.175)
            self.server.do_parallel_task(method=self.server.contact_another_server, args=(ip, '/election/answer', 'POST', data))
            self.start_election()

    #post on '/election/answer'
    def recv_answer(self):
        self.got_answer = True

    def coordinator(self):
        self.current_coordinator = self.server_ip
        uri = '/election/coordinator'
        data = {'coordinator': self.server_ip}

        print('-------- Coordinator (attribute: {})-----------'.format(str(self.coordinator_attribute)))
        self.server.propagate_to_all_servers(uri, req='POST', params_dict=data)
        print("Election ended in: {} seconds".format(str((time.time() - self.election_timer))))
        self.reset_election(self.server_ip)

    def recv_coordinator(self):
        coordinator = request.forms.get('coordinator')
        print('-------- Worker -----------' + str(self.coordinator_attribute))
        print('-------- New Coordinator is {} ------'.format(str(coordinator)))
        self.reset_election(coordinator)

    #post on '/election/coordinator'
    def reset_election(self, ip):
        self.current_coordinator = ip
        self.server.set_coordinator(ip)
        self.got_answer = False
        self.coordinator_counter = 0

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
        bottle.run(app = application,
                    server = 'paste',
                    host = server_ip,
                    port=PORT)
    except Exception as e:
        print("[ERROR] "+str(e))


# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
