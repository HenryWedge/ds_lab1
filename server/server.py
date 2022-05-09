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
# ------------------------------------------------------------------------------------------------------


class Blackboard():

    def __init__(self):
        self.content = dict()
        self.lock = Lock() # use lock when you modify the content


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
class Election():
    def __init__(self,server_ip,server_list):
        self.server_ip = server_ip
        self.server_list = server_list
        self.server_id = int(self.server_ip.split('.')[-1])
        self.leader_attribute = self.server_id # TODO:  Should be random between [0,20]
        self.server_Dict = dict() #[10.0.0.1 : 21 , 10.0.0.2 : 21 ,....]
        self.current_leader = -1
        self.is_leader = False


    def get_leader_Attribute(self):
        #print('LE Atribute:' + str(self.leader_attribute))
        return str(self.leader_attribute)

    def init_election(self):
        self.ping_AllServers()

    def start_election(self):
        self.election()

    def ping_AllServers(self):
        for s in self.server_list:
            if not(s==self.server_ip):
                answer_leader_attribute = self.ping_server(s)
                self.server_Dict[s] = answer_leader_attribute

    def election(self):
        for s in self.server_Dict:
            if self.server_Dict[s] > self.leader_attribute:
                success = False
                try:
                    res = requests.post('http://{}{}'.format(srv_ip, URI),
                                            data={self.server_ip : self.leader_attribute})
                    if res.status_code == 200:
                        success = True
                except Exception as e:
                    print("[ERROR] "+str(e))
            print(success)
        return

    def answer(self):
        return

    def coordinator(self):
        return


    def ping_server(self,serv_ip):
        data = dict()
        URI  = '/electionattribute'
        try:
            res = requests.get('http://{}{}'.format(serv_ip, URI))
            if res.status_code == 200:
                success = True
                return int(res.content)
        except Exception as e:
            print("[ERROR] "+str(e))

        return -1







# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.election = Election(IP,servers_list)
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
        #Election
        self.get('/electionattribute', callback=self.election.get_leader_Attribute)
        self.get('/testelection', callback =self.election.start_election)


        #-------------------------------------------------
        self.do_parallel_task_after_delay(2, self.election.init_election,args=())


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
                                    data=params_dict.dict)
            elif 'GET' in req:
                res = requests.get('http://{}{}'.format(srv_ip, URI))
            # result can be accessed res.json()
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
        self.add_entry()
        self.propagate_to_all_servers(URI='/board', req='POST', params_dict=request.forms)

    def modify_entry(self, param):
        entry = request.params.get('entry')
        isModify = request.params.get('delete') == '0'
        self.blackboard.delete_content(param)

        if (isModify):
            self.blackboard.modify_content(entry, entry)
        return

    def modify_entry_with_propagation(self, param):
        self.modify_entry(param)
        self.propagate_to_all_servers(URI='/board/{}/'.format(param), req='POST', params_dict=request.forms)

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
                    port = PORT)
    except Exception as e:
        print("[ERROR] "+str(e))


# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
