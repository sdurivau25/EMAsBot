# coding=utf-8

### Declarations des variables ###

bots = []
indicators = {}
clientk0, bot_token1, bot_token2 = 'None', 'None', 'None'
columns = ['owner', 'client', 'bot_chatID1', 'base', 'quote', 'total_base', 'total_quote', 'paire', 'your_base', 'your_quote', 'margin_base',  'margin_quote', 'indicators[paire]']

### Importations ### 

# Modules externes
import base64
import calendar
import hashlib
import hmac
import time
from datetime import datetime
import uuid
import json
import requests
from threading import Thread, RLock
from time import strftime, sleep

# Modules Clients
import kucoin_client as kc

### Fonctions ###
from ok_tradingbot_functions import *

def quick_launch():
    ready = input('Have you got an all-ready dictionary ? (y/n)')
    if ready == 'y' :
        bypass = False
        bypassmode = input('Bypass mode ? (y/n)')
        bypass = True if bypassmode=='y' else False
        package = input('Please input your package encrypted token, from "csv_to_dict" then "crypter" :')
        mdp = input('Please input your password :')
        check = input('Are you sure of your credentials ? (y/n)')
        if check == 'y':
            try :
                package = decrypter(mdp, package, 'dict')
            except Exception as e:
                log_func(e,urlID)
                raise SystemExit('Error during pack extracting, probably a wrong password, known as : {}'.format(e))
            print("Package has been loaded ; I'm gonna start the bots from the package")
            log_func('Gonna start bots from package', urlID)
            for i in range(len(package)):
                launch_pack, columns_pack = {}, ['client']
                for x in columns :
                    if x in package[str(i)]: 
                        columns_pack.append(x)
                for category in columns_pack :
                    if category != 'client':
                        launch_pack[category] = package[str(i)][category]
                    elif category == 'client':
                        launch_pack[category] = kc.Client(package[str(i)]['public'], package[str(i)]['secret'], package[str(i)]['password'], package[str(i)]['sandbox'])
                pack = launch_pack
                check = input('Is everything ok ? (y/n)')
                pack = start_bot(pack)
                if check == 'y' :
                    try :
                        n=KucoinBot(pack['owner'], pack['client'], pack['bot_chatID1'], pack['base'], pack['quote'], pack['your_base'], pack['your_quote'], pack['margin_base'], pack['margin_quote'], pack['indicators[paire]'], bypass=bypass)
                        n.start()
                        bots.append(n)
                    except ValueError as e:
                        print('Error line 67, {}'.format(e))
                        log_func('Error line 67, {}'.format(e), urlID)
                        return
                    check = '0'
                else :
                    print('Bot aborted')
    else :
        pass

def start_bot(launch_pack={}):
    global bots
    global indicators
    ready_pack={}
    if launch_pack == {}:
        exchange = None
        owner = input('Whose bot is this one ?')
        sandbox = input('Sandbox mode ? (y/n)')
        if sandbox == 'y' : 
            sandbox = True
        else :
            sandbox = False
        client = kc.Client(input('Quelle est votre cle publique? : '),input('Quelle est votre cle privee? : '), input('Quelle est votre mot de passe ? : '), sandbox=sandbox)
        bot_chatID1 = input('User chatID ?')
        base = input('Base asset name (code, in MAJ, no space) ?')
        quote = input('Quote asset name (code, in MAJ, no space) ?')
        paire = '{}-{}'.format(quote,base)
        your_base = input('Amount of base you use ?')
        your_quote = input('Amount of quote you use ?')
        margin_base = input('Amount of base borrowed ?')
        margin_quote = input('Amount of quote borrowed ?')
        if paire not in indicators:
            indicators[paire] = kIndicators(paire='{}-{}'.format(quote, base))
            indicators[paire].start()
        ready_pack={'owner':owner, 'client':client, 'bot_chatID1':bot_chatID1, 'base':base, 'quote':quote,
        'paire':paire, 'your_base':your_base, 'your_quote':your_quote,  'margin_base':margin_base, 'margin_quote':margin_quote, 'indicators[paire]':indicators[paire]}
        return ready_pack
    elif launch_pack != {} :
        for x in ['owner', 'client', 'bot_chatID1', 'base', 'quote', 'paire', 'your_base', 'your_quote', 'margin_base', 'margin_quote']:
            if x in launch_pack:
                ready_pack[x] = launch_pack[x]
            elif x == 'paire':
                launch_pack[x] = '{}-{}'.format(launch_pack['quote'],launch_pack['base'])
                ready_pack[x] = launch_pack[x]
        if launch_pack['paire'] not in indicators:
            indicators[launch_pack['paire']] = kIndicators(launch_pack['paire'])
            indicators[launch_pack['paire']].start()
        ready_pack['indicators[paire]'] = indicators[launch_pack['paire']]
        if 'bypass' in launch_pack:
            ready_pack['bypass'] = launch_pack['bypass']
        return ready_pack


def interpreteur():
    global bots
    global indicators
    global stan_chatID
    while True:
        comm = input('@ : ')
        if comm == 'help':
            print("""Aide : liste des commandes : 
                - quick launch
                - start : Start a new bot
                - pause [id/all]
                - resume [id/all]
                - kill [id/all]
                - list
                - log
                - dellog
                - startsendlog [delay_in_min] : send log via telegram ; !! must have created a bot first !!
                - stopsendlog : stop sending log via telegram
                - startbypass : start bot with bypass mode
                - startbypass+#
                - startnotifbot
                - stopnotifbot
                - change tokens
                """)
        elif comm == 'quick launch':
            quick_launch()
        elif comm == 'start':
            bots = bots
            bot_token2 = bot_token2
            check = '0'
            pack = start_bot()
            check = input('Is everything ok ? (y/n)')
            if check == 'y' :
                if  pack['exchange'] == 'kucoin':
                    try :
                        n=KucoinBot(pack['owner'], pack['client'], pack['bot_chatID1'], pack['base'], pack['quote'], pack['your_base'], pack['your_quote'], pack['margin_base'], pack['margin_quote'], pack['indicators[paire]'], bypass=False)
                        n.start()
                        bots.append(n)
                    except Exception as e:
                        print(e)
                check = '0'
            else :
                print('Bot aborted')        
        elif comm.startswith('pause'):
            if comm=='pause all':
                for b in bots:
                    b.paused=True
                    b.telegram_bot_sendtext('Your bot, trading {}, has been paused'.format(b.paire))
                    b.log('bot {} paused'.format(id(b)))
            elif ' ' not in comm:
                print('G pa capte')
            else:
                for b in bots:
                    if str(id(b))==comm.split(' ')[1]:
                        b.paused = True
                        b.telegram_bot_sendtext('Your bot, trading {}, has been paused'.format(b.paire))
                        b.log('bot {} paused'.format(id(b)))
                        break
                else:
                    print("Ce bot n'existe pas")
        elif comm.startswith('resume'):
            if comm=='resume all':
                for b in bots:
                    b.paused=False
                    b.telegram_bot_sendtext('Your bot, trading {}, has been resumed'.format(b.paire))
                    b.log('bot {} resumed'.format(id(b)))
            elif ' ' not in comm:
                print('G pa capte')
            else:
                for b in bots:
                    if str(id(b))==comm.split(' ')[1]:
                        b.paused = False
                        b.telegram_bot_sendtext('Your bot, trading {}, has been resumed'.format(b.paire))
                        b.log('bot {} resumed'.format(id(b)))
                        break
                else:
                    print("Ce bot n'existe pas")
        elif comm.startswith('kill'):
            if comm=='kill all':
                check = 'n'
                check = input('you sure ? (y/n)')
                if check == 'n':
                    print('operation aborted')
                    continue
                withoutnotif = input('Whithout notification ? (if whithout : input "n")')
                silently = True if withoutnotif=='n' else False
                if silently == True :
                    for b in bots:
                        b.continuer = False
                        b.log('bot {} killed'.format(id(b)))
                        del b
                else :
                    for b in bots:
                        b.continuer = False
                        b.log('bot {} killed'.format(id(b)))
                        b.telegram_bot_sendtext('Your bot, trading {}, has been killed'.format(b.paire))
                        del b
                del withoutnotif
                del silently
                bots=[]
            elif ' ' not in comm:
                print('G pa capte')
            else:
                check = 'n'
                check = input('you sure ? (y/n)')
                if check == 'n':
                    print('operation aborted')
                    continue
                for i in range(len(bots)):
                    if str(id(bots[i])) == comm.split(' ')[1]:
                        bots[i].continuer = False
                        b.telegram_bot_sendtext('Your bot, trading {}, has been killed'.format(b.paire))
                        b.log('bot {} killed'.format(id(b)))
                        del bots[i]
                        break
                else:
                    print("Ce bot n'existe pas")
        elif comm == 'list':
            for b in bots:
                print('Bot {}, {}, is trading on {}. status : {}, chat_id : {} '.format(id(b), b.owner, b.paire, ['ENABLED', 'PAUSED'][b.paused], b.bot_chatID))
        elif comm=='log':
            with open('log.txt','r') as f:
                print(f.read())
        elif comm == 'dellog':
            with open('log.txt','w+') as f:
                f.write('')
        # elif comm.startswith('startsendlog'):
        #     bot_token = bot_token2
        #     bot_chatID = input('bot chat_id ?')
        #     log_bot = LogBot(int(comm.split(' ')[1]), bot_token, bot_chatID)
        #     log_bot.start()
        # elif comm == 'stopsendlog':
        #     if 'log_bot' not in globals():
        #         print('Error : log bot never started')
        #     else:
        #         log_bot.continuer = False
        #         del log_bot
        elif comm == 'startbypass':
            check = 'n'
            check = input('you sure ? (y/n)')
            if check == 'n':
                print('operation aborted')
                continue
            check = '0'
            pack = start_bot()
            check = input('Is everything ok ? (y/n)')
            if check == 'y' :
                try :
                    n=KucoinBot(pack['owner'], pack['client'], pack['bot_chatID1'], pack['base'], pack['quote'], pack['your_base'], pack['your_quote'], pack['margin_base'], pack['margin_quote'], pack['indicators[paire]'], bypass=True)
                    n.start()
                    bots.append(n)
                except Exception as e:
                    print(e)
                check = '0'
            else :
                print('Bot aborted')
        elif comm == 'startbypass+#':
            check = 'n'
            check = input('you sure ? (y/n)')
            if check == 'n':
                print('operation aborted')
                continue
            check, mode, csv, mdp, package = '0.0','0.0','0.0','0.0','0.0'
            mode = input('What was the previous position ?')
            csv = input('Input your crypted dict token :')
            mdp = input('Please input the dict password :')
            check = 'n'
            check = input('Is everything ok ? (y/n)')
            if check == 'n':
                print('operation aborted')
                continue
            package = decrypter(mdp, csv, 'dict')
            for i in range(len(package)):
                client, quote, base, paire, order_size, columns_pack, pack = '0.0','0.0','0.0','0.0',0.0, ['client'], {} 
                for x in columns :
                    if x in package[str(i)]: 
                        columns_pack.append(x)
                for category in columns_pack :
                    if category == 'quote':
                        quote = package[str(i)][category]
                    elif category == 'base':
                        base = package[str(i)][category]
                    elif category == 'client':
                        client = kc.Client(package[str(i)]['public'], package[str(i)]['secret'], package[str(i)]['password'], package[str(i)]['sandbox'])
                        account = get_margin_account(client)
                    else :
                        pack[category] = package[str(i)][category]
                paire = '{}-{}'.format(quote,base)
                if mode == 'short' :
                    precision = get_precision(paire, 'base', client)
                elif category == 'total_quote' and mode == 'long' :
                    precision = get_precision(paire, 'quote', client)
                if mode == 'short' :
                    for i in range(len(account)):
                        if account[str(i)]['currency'] == base:
                            available = float(account[str(i)]['available'])
                    minimum = float(client.get_currency(quote)['withdrawalMinSize'])
                    order_size = float(package[str(i)]['margin_quote'])
                elif mode == 'long' :
                    minimum = float(client.get_currency(quote)['withdrawalMinSize'])
                    for i in range(len(account)):
                        if account[str(i)]['currency'] == quote:
                            available = float(account[str(i)]['available'])
                            order_size = float(account[str(i)]['available']) - float(package[str(i)]['margin_quote'])
                order_size = round_x_to_y_number(order_size, precision)
                if (is_client(client)==True) :
                    if (float(order_size)>minimum and float(order_size)<available) :
                        if mode == 'short':
                            client.create_market_order(symbol=paire, side="buy", funds=float(order_size))
                        elif mode == 'long':
                            client.create_market_order(symbol=paire, side="sell", size=float(order_size))
                        sleep(3)
                    hold, currency, types, balance = [], [], [], {}
                    hold = [x['balance'] for x in client.get_accounts()]
                    currency = [x['currency'] for x in client.get_accounts()]
                    types = [x['type'] for x in client.get_accounts()]
                    for i in range(1,len(currency)+1):
                        if currency[-i] == quote and types[-i] == 'margin' :
                            balance[quote] = float(hold[-i])
                        elif currency[-i] == base and types[-i] == 'margin' :
                            balance[base] = float(hold[-i])
                    z = float(balance[base]) - float(pack['margin_base'])
                    your_base_pack = z if z>0 else 0.0
                    z = float(balance[quote]) - float(pack['margin_quote'])
                    your_quote_pack = z if z>0 else 0.0
                    try :
                        for x in columns:
                            if x not in pack:
                                pack[x] = '0.0'
                        launch_pack = {'owner':pack['owner'], 'client':client, 'bot_chatID1' : pack['bot_chatID1'], 'base' :base, 'quote':quote, 'your_base':your_base_pack, 'your_quote':your_quote_pack, 'margin_base':pack['margin_base'], 'margin_quote':pack['margin_quote'], 'indicators[paire]':pack['indicators[paire]'], 'bypass':True}
                        launch_pack = start_bot(launch_pack)
                        n=KucoinBot(launch_pack['owner'], launch_pack['client'], launch_pack['bot_chatID1'], launch_pack['base'],launch_pack['quote'], launch_pack['your_base'], launch_pack['your_quote'], launch_pack['margin_base'], launch_pack['margin_quote'], launch_pack['indicators[paire]'], bypass=True)
                        print("{}'s Bot started on {}-{}".format(launch_pack['owner'], launch_pack['quote'], launch_pack['base']))
                        n.start()
                        bots.append(n)
                        del precision, client, base,  quote, your_base_pack,  your_quote_pack, pack, launch_pack
                    except Exception as e:
                        print(e)
            del package
            del csv
            del mdp

        # elif comm.startswith('startnotifbot'):
        #     if 'notifbot' not in globals():
        #         notifbot = NotifBot()
        #         notifbot.start()
        #         print('notifbot started')
        #     else : 
        #         notifbot.continuer = False
        #         del notifbot
        #         notifbot = NotifBot()
        #         notifbot.start()
        #         print('notifbot started')
        # elif comm == 'stopnotifbot':
        #     if 'notifbot' not in globals():
        #         print('Error : notif bot never started')
        #     else:
        #         notifbot.continuer = False
        #         del notifbot
        #         print('notifbot stopped')
        elif comm == 'change tokens': 
            for b in bots:
                b.paused=True
            print('Bots paused')
            # if 'notifbot' not in globals():
            #     print('Notif bot never started, so has not been killed')
            # else:
            #     notifbot.continuer = False
            #     del notifbot
            bot_token1 = input('Bot_token 1 ? (Notif)')
            bot_token1 = str(bot_token1)
            bot_token2 = input('Bot_token 2 ? (Logs)')
            print('Tokens changed')
            for b in bots:
                b.bot_token = bot_token1
                b.paused=False
            urlID = 'https://api.telegram.org/bot' + bot_token2 + '/sendMessage?chat_id=' + stan_chatID
            # notifbot = NotifBot()
            # notifbot.start()
            print('notifbot started')
        else:
            print('Commande inconnue, veuillez taper "help" pour voir la liste des commandes')
    print('Programme termine')


### Classes ###

# Indicateurs
class kIndicators(Thread):
    """Indicators from Kucoin's price"""
    
    def __init__(self, paire, client=clientk0):
        Thread.__init__(self)
        self.client = clientk0
        self.paire = paire
        self.ema20 = 0.0
        self.ema45 = 0.0
        self.ema130 = 0.0
        self.get_2h_prices()
        self.calc_2h_emas()
        
    def log(self, message):
        message=str(message)
        log_func2(strftime('[%d/%m %H:%M:%S] Bot {} : {}'.format(id(self), message)))
        
    def get_2h_prices(self):
        a =int(time.time())
        self.prices = [float(x[2]) for x in self.client.get_kline_data(symbol=self.paire, kline_type='2hour', start=int(a-1879200), end=int(a))]   
        
    def calc_2h_emas(self):        
         #1 : calcul des sma qui serviront de première ema
        self.Nsma20=0.0
        for i in range(19,39):
            self.Nsma20 += self.prices[i]
        self.Nsma20 = self.Nsma20/20
        
        self.Nsma45=0.0
        for i in range(44,89):
            self.Nsma45 += self.prices[i]
        self.Nsma45 = self.Nsma45/45
        
        self.Nsma130=0.0
        for i in range(129,259):
            self.Nsma130 += self.prices[i]
        self.Nsma130 = self.Nsma130/130
        
         # 2 : Calcul des multiplicateurs
        self.m20 = 2/(20+1)
        self.m45= 2/(45+1)
        self.m130= 2/(130+1)
         # 3 : Calcul des ema
        self.Nema20=self.Nsma20
        for i in range(1,20):
            self.Nema20 = (self.prices[20-i]-self.Nema20)*self.m20 + self.Nema20
            
        self.Nema45=self.Nsma45
        for i in range(1,45):
            self.Nema45 = (self.prices[45-i]-self.Nema45)*self.m45 + self.Nema45
            
        self.Nema130=self.Nsma130
        for i in range(1,130):
            self.Nema130 = (self.prices[130-i]-self.Nema130)*self.m130 + self.Nema130
        
        if self.Nema20 != self.ema20 or self.Nema45 != self.ema45 or self.Nema130 != self.ema130 :
            self.ema20 = self.Nema20
            self.ema45 = self.Nema45
            self.ema130 = self.Nema130
            self.log("EMAs moved")
            
    def run(self):
        while True :
            try :
                self.get_2h_prices()
                self.calc_2h_emas()
            except Exception as e:
                self.log(e)
                pass                
            sleep(8)


# Bots
class KucoinBot(Thread) :
    """TradingBot for Kucoin"""

    def __init__(self, owner, client, bot_chatID1, base, quote, your_base, your_quote, margin_base, margin_quote, indicators, bypass=False) :
        Thread.__init__(self)
        self.owner = owner
        self.client = client
        self.bot_token = bot_token1
        self.bot_chatID = bot_chatID1
        self.base = str(base)
        self.quote = str(quote)
        self.paire = '{}-{}'.format(self.quote,self.base)
        self.indicators = indicators
        self.your_base = float(your_base)
        self.your_quote = float(your_quote)
        self.margin_base = float(margin_base)
        self.margin_quote = float(margin_quote)
        self.base_qty = float(your_base) + float(margin_base)
        self.quote_qty = float(self.your_quote)+float(self.margin_quote)
        self.min_base = float(self.client.get_currency(self.base)['withdrawalMinSize'])
        self.min_quote = float(self.client.get_currency(self.quote)['withdrawalMinSize'])
        self.bypass = bypass
        self.firstvalue = float(self.your_base)+float(self.your_quote)*float(self.client.get_ticker(self.paire)['price'])
        self.continuer=True
        self.paused = False
        self.get = 'https://api.telegram.org/bot' + self.bot_token + '/getUpdates?limit=100'
        self.response = requests.get(self.get)
        self.max=int(len(self.response.json()['result']))
        try :
            for i in range(1,self.max):
                if str(self.response.json()['result'][-i]['message']['chat']['id']) == str(self.bot_chatID) :
                    self.last_telegram_id = str(self.response.json()['result'][-i]['message']['date'])
                    break
                else :
                    self.last_telegram_id= '000'
        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except :
            self.last_telegram_id= '000'
            pass
        self.answer = 'Please wait...'
                
    def log(self, message):
        global urlID
        message = str(message)
        log_func(strftime('[%d/%m %H:%M:%S] Bot {} : {}'.format(id(self), message)), urlID)
        
    def wallet(self):
        self.firstvalue = self.firstvalue
        self.walletvalue1 = (float(self.base_qty)-float(self.margin_base))+(float(self.quote_qty) - float(self.margin_quote))*float(self.client.get_ticker(self.paire)['price'])
        self.walletvalue = round_x_to_y_decimal(self.walletvalue1,5)
        if self.firstvalue != 0.0:
            self.roi = (round_x_to_y_decimal(self.walletvalue1/self.firstvalue, 5) - 1)*100
        else :
            self.roi = '0'
    
    def telegram_bot_sendtext(self, bot_message):
        self.bot_token = bot_token1
        self.send_text = 'https://api.telegram.org/bot' + self.bot_token + '/sendMessage?chat_id=' + self.bot_chatID + '&parse_mode=Markdown&text=' + bot_message
        self.response = requests.get(self.send_text)
        return self.response.json()
        
    def telegram_answer(self):
        self.answer = "I'm ready"
        self.id={}
        self.get = 'https://api.telegram.org/bot' + self.bot_token + '/getUpdates?limit=100'
        self.response = requests.get(self.get)
        if not isinstance(self.response.json()['result'], list):
            return
        try :
            self.max=int(len(self.response.json()['result']))
            if self.max>2:
                for i in range(1,self.max):
                    self.id = self.response.json()['result'][-i]['message']
                    if str(self.id['date']) > str(self.last_telegram_id) and str(self.id['chat']['id']) == str(self.bot_chatID):
                        self.wallet()
                        if str(self.id['text']) == '/roi' :
                            if self.roi != '0':
                                self.answer  = 'On {} : you made +{}% of profit'.format(self.paire,round_x_to_y_decimal(self.roi, 2))
                            else :
                                self.answer = 'On {} : your wallet is empty'.format(self.paire)
                        elif str(self.id['text']) == '/wallet' :
                            self.answer = 'On {} : your wallet is worth {} {} : you have {} {} and {} {}'.format(self.paire, round_x_to_y_decimal(self.walletvalue, 2), self.base,  round_x_to_y_decimal(self.quote_qty, 4), self.quote, round_x_to_y_decimal(self.base_qty, 2), self.base)
                        elif str(self.id['text']) == '/credits':
                            self.answer = """Credits to Stanislas du Rivau. Please consider tipping me for my work :
                
    BTC
    1F7b9ocDCqLtoDX9kbCQJo1T9q5ZMZjezm

    ETH 

    0x565c5E1d3484dE8b144dD00753f0CcDd518c24C6

    Xrp

    rMdG3ju8pgyVh29ELPWaDuA74CpWW6Fxns

    Tag :

    3061811188

    Any help appreciated. Thank you !"""
                        elif str(self.id['text']) == '/commands' :
                            self.answer = """Commands :
    /wallet : get your current wallet value, minus what you borrowed
    /roi : get your current Return On Investment
    /credits"""
                        elif str(self.id['text']) == 'emas' : 
                            self.answer = '20={}, 45={}, 130={}'.format(self.indicators.ema20, self.indicators.ema45, self.indicators.ema130)
                        elif str(self.id['text']) == 'stop_all#warning' and str(self.bot_chatID) == '1148095114' :
                            for b in bots:
                                b.stop_long, b.stop_short = True, True
                                b.check_to_do()
                                b.place_order()
                                b.conclude()
                        else :
                            self.answer = 'Unknown command, type /commands to get commands'
                        self.telegram_bot_sendtext(self.answer)
                        self.last_telegram_id = str(self.id['date'])
                        break
        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except Exception as e:
            self.log(e)
        
    def analyze_market(self):
        self.base_qty = float(self.base_qty)
        self.quote_qty = float(self.quote_qty)
        self.min_base = float(self.min_base)
        self.min_quote = float(self.min_quote)
        self.full_long = False 
        self.full_short = False
        self.stop_long=False
        self.stop_short=False
        self.buy_all=False
        self.sell_all=False
        self.sell_long=False
        self.sell_short=False
        self.order_size=float(0.0)
        if self.indicators.ema20>self.indicators.ema45 and self.indicators.ema45>self.indicators.ema130 :
            self.full_long = True
        else :
            self.full_long = False
        if self.indicators.ema20<self.indicators.ema45 and self.indicators.ema45<self.indicators.ema130 :
            self.full_short = True
        else :
            self.full_short = False
        if not self.full_long and not self.full_short :
            if self.base_qty < self.margin_base:
                self.stop_long=True
            elif self.quote_qty < self.margin_quote :
                self.stop_short=True
            
    def check_to_do(self):
        if self.full_long and (self.base_qty > self.min_base) :
            self.buy_all=True
            self.order_size=0.999*(round_x_to_y_number(self.base_qty, 6))
            self.log("Long, {}".format(self.paire))
        elif self.full_short and self.quote_qty > self.min_quote :
            self.sell_all=True
            self.order_size=0.999*round_x_to_y_number(self.quote_qty, 6)
            self.log("Short, {}".format(self.paire))
        elif self.stop_long and (self.quote_qty > self.margin_quote) and (float(self.quote_qty) - float(self.margin_quote) > float(self.min_quote)):
            self.order_size=0.999*round_x_to_y_number(float(self.quote_qty)-float(self.margin_quote), 6)
            self.sell_long=True
            self.log("Stop long, {}".format(self.paire))
        elif self.stop_short and (self.base_qty>self.margin_base) and ((self.base_qty-self.margin_base)>self.min_base) :
            self.order_size=0.999*round_x_to_y_number(self.base_qty-self.margin_base, 6)
            self.sell_short=True
            self.log("Stop short, {}".format(self.paire))
            
        #check client's wallet
        self.hold, self.currency, self.type, self.balance = [], [], [], {}
        self.hold = [x['balance'] for x in self.client.get_accounts()]
        self.currency = [x['currency'] for x in self.client.get_accounts()]
        self.type = [x['type'] for x in self.client.get_accounts()]
        self.compteur = len(self.currency)
        for i in range(1,self.compteur+1):
            if self.currency[-i] == self.quote and self.type[-i] == 'margin' :
                self.balance[self.quote] = float(self.hold[-i])
            elif self.currency[-i] == self.base and self.type[-i] == 'margin' :
                self.balance[self.base] = float(self.hold[-i])
        if (self.buy_all or self.sell_short) and (self.balance[self.base]<self.order_size):
            self.buy_all, self.sell_short = False, False
            self.log('Balance insufficient for a buy')
        elif (self.sell_all or self.sell_long) and (self.balance[self.quote]<self.order_size):
            self.sell_all, self.sell_long = False, False
            self.log('Balance insufficient for a sell')
            
    def place_order(self, silently=False):
        if self.buy_all or self.sell_short :
            self.log('Gonna place a buy order')
            self.client.create_market_order(self.paire, kc.Client.SIDE_BUY, funds=self.order_size)
            sleep(1.5)
            self.lastorder = self.client.get_orders(symbol=self.paire)['items'][0]
            self.lastprice = self.client.get_ticker(self.paire)['price']
            if not silently:
                self.telegram_bot_sendtext('Hey {} , I bought {}{} at price {}, using {}{}'.format(self.owner, self.lastorder['dealSize'],self.quote, self.lastprice, self.lastorder['dealFunds'], self.base))
            self.log('{} bought {}{} at price {}, using {}{}'.format(self.owner, self.lastorder['dealSize'],self.quote, self.lastprice, self.lastorder['dealFunds'], self.base))
        elif self.sell_all or self.sell_long :
            self.log('Gonna place a sell order')
            self.client.create_market_order(self.paire, kc.Client.SIDE_SELL, size=self.order_size)
            sleep(1.5)
            self.lastorder = self.client.get_orders(symbol=self.paire)['items'][0]
            self.lastprice = self.client.get_ticker(self.paire)['price']
            if not silently :
                self.telegram_bot_sendtext('Hey {} , I sold {}{} at price {}, winning {}{}'.format(self.owner, self.lastorder['dealSize'],self.quote, self.lastprice, self.lastorder['dealFunds'], self.base))
            self.log('{} sold {}{} at price {}, winning {}{}'.format(self.owner, self.lastorder['dealSize'],self.quote, self.lastprice, self.lastorder['dealFunds'], self.base))
            
    def conclude(self):
        sleep(1.5)
        if self.buy_all or self.sell_short:
            self.base_qty = float(self.base_qty)-float(self.lastorder['dealFunds'])
            self.quote_qty = float(self.quote_qty)+float(self.lastorder['dealSize'])
            self.telegram_bot_sendtext('Wallet : {}{} and {}{}'.format(self.base_qty,self.base,self.quote_qty,self.quote))    
            self.log('Wallet : {}{} and {}{}'.format(self.base_qty,self.base,self.quote_qty,self.quote))
            self.telegram_bot_sendtext('All went well, waiting for new signals')
            self.log('All went well, waiting for new signals')
        if self.sell_all or self.sell_long :
            self.base_qty = float(self.base_qty)+float(self.lastorder['dealFunds'])
            self.quote_qty = float(self.quote_qty)-float(self.lastorder['dealSize'])
            self.telegram_bot_sendtext('Wallet : {}{} and {}{}'.format(self.base_qty,self.base,self.quote_qty,self.quote))    
            self.log('Wallet : {}{} and {}{}'.format(self.base_qty,self.base,self.quote_qty,self.quote))
            self.telegram_bot_sendtext('All went well, waiting for new signals')
            self.log('All went well, waiting for new signals')
        self.full_long = False 
        self.full_short = False
        self.stop_long=False
        self.stop_short=False
        self.buy_all=False
        self.sell_all=False
        self.sell_long=False
        self.sell_short=False
        self.order_size=0.0
        
    def run_all(self):
        while self.continuer :
            try :
                while self.continuer:
                    sleep(10.0)
                    while self.paused:
                        sleep(10)
                    self.analyze_market()
                    self.check_to_do()
                    self.place_order()
                    self.conclude()
                self.log('Operations terminees, bot en veille...')
            except KeyboardInterrupt:
                raise KeyboardInterrupt
            except Exception as e:
                self.log(e)
            sleep(2)
            
           
    def run(self):
        self.log('Bot is ready and looking for entry point')
        self.telegram_bot_sendtext(' Hey {} ! Your bot, trading {}, is ready and looking for entry point, this can take days, be patient ! It is worth waiting.'.format(self.owner, self.paire))
        self.telegram_bot_sendtext("""Few rules about me :
        - You can get the list of available commands sending /commands
        - Please wait for the answer before aking me new things ! it won't lead to bugs but only the last question will have its answer.
        - This bot works on a mid-term basis. It usually  trades once a week, sometimes more, sometimes less : wait and accumulate !""")
        sleep(7)
        self.analyze_market()
        if self.bypass :
            self.log('Bypass mode')
            self.telegram_bot_sendtext("Bypass mode : you won't wait for the best entry point")
            self.log('Bot is ready...')
            self.run_all()
        elif self.full_long :
            while self.full_long :
                sleep(10)
                self.analyze_market()
            self.log('Bot found its entry point')
            self.telegram_bot_sendtext('Bot found its entry point')
            self.log('Bot is ready...')
            self.run_all()
        elif self.full_short :
            while self.full_short :
                sleep(10)
                self.analyze_market()
            self.log('Bot found its entry point')
            self.telegram_bot_sendtext('Bot found its entry point')
            self.log('Bot is ready...')
            self.run_all()
        else :
            self.log('Bot found its entry point')
            self.telegram_bot_sendtext('Bot found its entry point')
            self.log('Bot is ready...')
            self.run_all()
            
class NotifBot(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.continuer=True
                    
    def run(self):
        while self.continuer == True:
            for b in bots:
                b.telegram_answer()             
            sleep(0.5)
            
# class LogBot(Thread):
#     def __init__(self, delay, bot_token, bot_chatID):
#         Thread.__init__(self)
#         self.delay = delay
#         self.bot_token = bot_token2
#         self.bot_chatID = bot_chatID
#         self.continuer=True
    
#     def send_msg(self, msg):
#         self.msg=msg
#         send_text = 'https://api.telegram.org/bot' + self.bot_token + '/sendMessage?chat_id=' + self.bot_chatID + '&parse_mode=Markdown&text=' + self.msg
#         response = requests.get(send_text)
#         return response.json()
    
#     def send_log(self):
#         msg1 = read_log()
#         self.send_msg(msg1)
#         msg2 = read_log2()
#         self.send_msg(msg2)
 
#     def run(self):
#         while self.continuer:
#             self.send_log()
#             sleep(self.delay*60)


### Bot Starter ###

# Initialisation
bots = []
indicators = {}
clientk0, bot_token1, bot_token2 = 'None', 'None', 'None'
columns = ['owner', 'client', 'bot_chatID1', 'base', 'quote', 'paire', 'your_base', 'your_quote', 'margin_base',  'margin_quote', 'indicators[paire]', 'total_base', 'total_quote']
token = init_of_tradingbots()
clientk0, bot_token1, bot_token2, urlID, stan_chatID = token['clientk0'], str(token['bot_token1']), str(token['bot_token2']), str(token['urlID']), str(token['stan_chatID'])
del token
log_func('Connecte', urlID)
log_func2('Connecte')
quick_launch()

# Interpreteur
notifbot = NotifBot()
notifbot.start()

interpreteur()
