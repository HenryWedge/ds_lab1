import requests


srv_ip  = '10.1.0.1:80'
URI     = '/board/propagate'
res     = requests.post('http://{}{}'.format(srv_ip, URI),data={'entry':'test1wdawa24'})

print(res)
