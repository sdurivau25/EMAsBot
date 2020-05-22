# coding=utf-8

### Importations ###
# Modules libres
from itsdangerous import URLSafeSerializer
import ast
import requests
import json

# Modules persos
import kucoin_client as kc

urlID = 'telegram url'

### tradingbot_functions ###
def init_of_tradingbots():
    global urlID
    token = {}
    mdp = input('Hey Master ! Please input your encrypting code. :')
    print('Loading Kucoin client0...')
    crypt = '.eJwdyrsNgDAMBcBZktSWXiLbxGIMJrDzKanYXyCuviwrJotL21EdHz14TEgqZ0mua5opCAEltgoytiCudUfXYZDxx-vxu3W0_AIlSBOP.N2aG6LE49_71YiWhEcm_uanqReU'
    try :
        api1 = decrypter(mdp, crypt, 'list')
    except Exception as e:
        raise SystemExit('Wrong password during Kucoin decrypter')
    clientk0 = kc.Client(api1[0], api1[1], api1[2], sandbox=True)
    token['clientk0'] = clientk0
    del crypt
    del api1
    print('Kucoin client0 loaded')
    print('Loading Telegram tokens')
    crypt = 'IjEwNTk5NzA2MDU6QUFFalZ1VWkzd0I0VXlOWGR6OHZjUnBDTm01SERrODFYOFkhIzsjITExNzY5ODI4MDM6QUFHaW1xLS1qNHMzTWZ5NDFaSXdNMnp5NGZTb1FnSkFNSzAhIzsjITExNDgwOTUxMTQi.7in9RwKGoggR35XGLPg2atwTDlM'
    api2 = decrypter(mdp, crypt, 'list')
    token['bot_token1'] = api2[0]
    token['bot_token2'] = api2[1]
    stan_chatID = api2[2]
    token['stan_chatID'] = stan_chatID
    urlID = 'https://api.telegram.org/bot' + api2[1] + '/sendMessage?chat_id=' + stan_chatID
    token['urlID'] = urlID
    del crypt, api2, urlID
    print('Telegram tokens loaded')
    return token



def stansendlog(urlID, bot_message):
    send_text = urlID + '&parse_mode=Markdown&text=' + bot_message
    response = requests.get(send_text)
    return response.json()

def log_func(msg, urlID):
    with open('log.txt','a') as f:
        f.write('{}\n'.format(msg))
    stansendlog(urlID, msg)
  
def read_log():
    with open('log.txt','r') as f:
        txt=f.read()
    return txt

def log_func2(msg):
    with open('log2.txt','a') as g:
        g.write('{}\n'.format(msg))
        
def read_log2():
    with open('log2.txt','r') as g:
        txt=g.read()
    return txt
        
def round_x_to_y_decimal(x,y):
    return float(int(x*10**y)/10**y)

def round_x_to_y_number(x,y):
    x, y = float(x), int(y)
    num = str(f"{x:.20f}")
    res = ''
    if y > len(num):
        y=len(num)
    for i in range(y):
        res += num[i]
    return res

def get_precision(paire, type='base or quote', client='client kucoin'):
    side = "null"
    z = client.get_symbols()
    if type  == 'base':
        side = "quoteIncrement"
    elif type == 'quote' :
        side = "baseIncrement"
    for i in range(len(z)):
        if z[i]['symbol'] == paire:
            precision = int(len(str(z[i][side])))
    if not precision > 0:
        log_func('Error in getting precision')
        precision = 0
    return precision

def crypter(mdp, uncrypted, typed="(optionnal) None or list"):
    if typed == 'list':
        uncrypted = '!#;#!'.join(uncrypted)
    passwd = URLSafeSerializer(mdp)
    crypted = passwd.dumps(str(uncrypted))
    del passwd
    del mdp
    return crypted

def decrypter(mdp, crypted, typed="(optionnal) None, list or dict"): #Can be list or dict
    mdp = str(mdp)
    passwd = URLSafeSerializer(mdp)
    decrypted = passwd.loads(str(crypted))
    del mdp
    del passwd
    if typed=='list':
        decrypted = list(decrypted.split('!#;#!'))        
    elif typed=='dict':
        decrypted = ast.literal_eval(decrypted)
    return decrypted

def is_client(client): #checke que le compte n'est pas vide
    import kucoin_client as kc
    if isinstance(client, kc.Client):
        if client.get_accounts() != {}:
            return True  
        else :
            return False
    else : 
        return False
    

def get_margin_account(client):
    a={}
    b={}
    if (is_client(client)) == True:
        for i in range(len(client.get_accounts())+1):
            b[str(i)] = {}
        for i in range(len(client.get_accounts())):
            if client.get_accounts()[i]['type']=='margin':
                z = client.get_accounts()[i]
                b[str(i)]['currency'] = z['currency']
                b[str(i)]['available'] = z['available']
        last ={}
        a=0
        for i in range(1,6):
            if b[str(i)] != {}:
                last[str(a)] = b[str(i)]
                a = a+1
        return last
    else :
        return {}
