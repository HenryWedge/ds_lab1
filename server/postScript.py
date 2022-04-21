from threading import Thread
import requests

def do_parallel_task(method):
    thread = Thread(target=method)
    thread.daemon = True
    thread.start()

def contact_another_server():
    requests.post('http://{}{}'.format("10.1.0.1", "/add_entry/propagate"), data={"entry": "Entry"})


def do_magic():
    for i in range(10):
        print(str(i + 1) + "th try")
        do_parallel_task(contact_another_server)

if __name__ == '__main__':
    do_magic()