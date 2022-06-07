# coding=utf-8
import argparse
import random
from threading import Lock, Thread
import time
import bottle
from bottle import Bottle, request, template, run, static_file
import requests

class Blackboard:
    def __init__(self):
        self.content = dict()
        self.lock = Lock()  # use lock when you modify the content

    def get_content(self):
        with self.lock:
            cnt = self.content
        return cnt

    def add_entry(self, new_id, new_entry):
        with self.lock:
            self.content[str(new_id)] = new_entry
        return

    def delete_entry(self, delete_id):
        with self.lock:
            self.content.pop(delete_id)
        return

    def set_content(self, content: dict):
        with self.lock:
            self.content = content
        return


class Server(Bottle):
    def __init__(self, server_id, ip, servers_list):
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.id = int(server_id)
        self.ip = str(ip)
        self.servers_list = servers_list
        self.clock = 0

        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board/propagate', callback=self.add_entry_with_propagation)
        self.post('/board/<param>/propagate', callback=self.modify_entry_with_propagation)
        self.post('/', callback=self.post_index)
        self.post('/update', callback=self.update_blackboard_content)
        self.get('/templates/<filename:path>', callback=self.get_template)

    # create a thread running a new task
    # Usage example: self.do_parallel_task(self.contact_another_server, args=("10.1.0.2", "/index", "POST", params_dict))
    # this would start a thread sending a post request to server 10.1.0.2 with URI /index and with params params_dict
    def do_parallel_task(self, method, args=None):
        thread = Thread(target=method,
                        args=args)
        thread.daemon = True
        thread.start()

    # create a thread, and run a task after a specified delay
    # Usage example: self.do_parallel_task_after_delay(10, self.start_election, args=(,))
    # this would start a thread starting an election after 10 seconds
    def do_parallel_task_after_delay(self, delay, method, args=None):
        thread = Thread(target=self._wrapper_delay_and_execute,
                        args=(delay, method, args))
        thread.daemon = True
        thread.start()

    def _wrapper_delay_and_execute(self, delay, method, args):
        time.sleep(delay)  # in sec
        method(*args)

    # Try to contact another serverthrough a POST or GET
    # usage: server.contact_another_server("10.1.1.1", "/index", "POST", params_dict)
    def contact_another_server(self, srv_ip, URI, req='POST', params_dict=None):
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
            print("[ERROR] " + str(e))
        return success

    def propagate_to_all_servers(self, URI, req='POST', params_dict=None):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip:  # don't propagate to yourself
                self.do_parallel_task(method=self.contact_another_server, args=(srv_ip, URI, req, params_dict))

    # route to ('/')
    def index(self):
        board = []
        for k, v in self.blackboard.get_content().items():
            board.append(Entry(k, v.entry, v.clock))
        return template('server/templates/index.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=board,
                        members_name_string='Julius Rüder and Hendrik Reiter')

    # get on ('/board')
    def get_board(self):
        board = []
        for k, v in self.blackboard.get_content().items():
            board.append(Entry(k, v.entry, v.clock))
        return template('server/templates/blackboard.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=board)

    def update_blackboard_content(self):
        clock = int(request.forms.get('clock'))
        print("####DEBUG#### \n  My clock: {} \n  Clock from request {}".format(self.clock, clock))
        if clock > self.clock:
            self.clock = clock
            dictionary = dict()
            for entry in request.forms:
                if entry not in ['clock', 'entry', 'delete']:
                    split_string = str(request.forms.get(str(entry))).split(" ")
                    dictionary[entry] = Entry(0, split_string[0], split_string[1])

            self.blackboard.set_content(dictionary)

    def add_entry_with_propagation(self):
        self.clock = self.clock + 1
        request_form = request.forms
        new_entry = request_form.get('entry')
        self.blackboard.add_entry(new_entry=Entry(0, new_entry, self.clock), new_id=random.randint(0, 9999))

        request_form['clock'] = self.clock
        print("Blackboard content: {}".format(self.blackboard.get_content()))

        for k, v in self.blackboard.get_content().items():
            request_form[k] = "{} {}".format(v.entry, v.clock)

        self.propagate_to_all_servers(URI='/update', req='POST', params_dict=request_form)

    def modify_entry_with_propagation(self, param):
        self.clock = self.clock + 1
        entry = request.params.get('entry')

        self.blackboard.delete_entry(param)

        if request.params.get('delete') == '0':
            self.blackboard.add_entry(param, Entry(0, entry, self.clock))

        request_form = request.forms
        request_form['clock'] = self.clock
        print("Blackboard content: {}".format(self.blackboard.get_content()))

        for k, v in self.blackboard.get_content().items():
            request_form[k] = "{} {}".format(v.entry, v.clock)

        self.propagate_to_all_servers(URI='/update', req='POST', params_dict=request_form)

    # post on ('/')
    def post_index(self):
        try:
            new_entry = request.forms.get('entry')
            print("Received: {}".format(new_entry))
        except Exception as e:
            print("[ERROR] " + str(e))

    def get_template(self, filename):
        return static_file(filename, root='./server/templates/')


class Entry:
    def __init__(self, id, entry, clock):
        self.id = id
        self.entry = entry
        self.clock = clock

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


if __name__ == '__main__':
    main()
