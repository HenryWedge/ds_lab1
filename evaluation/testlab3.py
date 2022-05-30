import requests
import threading
import time


def modify(n):
    requests.post('http://10.1.0.{}:80{}'.format(str(n),'/board/{}/propagate'.format('test')),data={'entry': str('test{}'.format(str(n))), 'delete':0})

srv1  = '10.1.0.1:80'
srv2  = '10.1.0.2:80'
srv3  = '10.1.0.3:80'

print('add server 1')
requests.post('http://10.1.0.{}:80{}'.format(1, '/board/propagate'),data={'entry':str('test')})
time.sleep(10)
print('t1')
x = threading.Thread(target=modify,args=(2,))
print('t2')
y = threading.Thread(target=modify,args=(3,))
print('t3')
print('modify server 2')
x.start()
time.sleep(0.25)
print('modify server 3')
y.start()
