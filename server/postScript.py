from threading import Thread
import requests

def do_parallel_task(delay, method, args=None):
    thread = Thread(target=method(*args),
                    args=(delay, method, args))
    thread.daemon = True
    thread.start()

def contact_another_server(URI, params_dict, srv_ip):
    res = requests.post('http://{}{}'.format(srv_ip, URI), data=params_dict)
    requests.post('http://{}{}'.format(srv_ip, URI), data=params_dict.dict)


def do_magic():
    for i in range(10):
        do_parallel_task(contact_another_server, args=("10.1.0.1", "/add_entry/propagate", "POST", {"entry": "Entry"}))