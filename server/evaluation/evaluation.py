import requests

srv_ip  = '10.1.0.1:80'
URI     = '/board/propagate'

for i in range(100):
	requests.post('http://{}{}'.format(srv_ip, URI),data={'entry':'entry: ' + str(i)})
