# coding=utf-8

import base64
import calendar
import hashlib
import hmac
import time
from datetime import datetime
import uuid
import json
import requests

# Kucoin Client
# Main functions :

# get_timestamp
# get_currency
# get_accounts
# create_market_order
# create_limit_order
# cancel_all_orders
# get_orders
# get_ticker
# get_kline_data

### System error codes ###
# Code	Meaning
# 400001	Any of KC-API-KEY, KC-API-SIGN, KC-API-TIMESTAMP, KC-API-PASSPHRASE is missing in your request header
# 400002	KC-API-TIMESTAMP Invalid -- Time differs from server time by more than 5 seconds
# 400003	KC-API-KEY not exists
# 400004	KC-API-PASSPHRASE error
# 400005	Signature error -- Please check your signature
# 400006	The requested ip address is not in the api whitelist
# 400007	Access Denied -- Your api key does not have sufficient permissions to access the uri
# 404000	Url Not Found -- The request resource could not be found
# 400100	Parameter Error -- You tried to access the resource with invalid parameters
# 411100	User are frozen -- User are frozen, please contact us via support center.
# 500000	Internal Server Error -- We had a problem with our server. Try again later.

### Kucoin Exceptions ###
class KucoinAPIException(Exception):
    """Exception class to handle general API Exceptions
        `code` values
        `message` format
    """
    def __init__(self, response):
        self.code = ''
        self.message = 'Unknown Error'
        try:
            json_res = response.json()
        except ValueError:
            self.message = response.content
        else:
            if 'error' in json_res:
                self.message = json_res['error']
            if 'msg' in json_res:
                self.message = json_res['msg']
            if 'message' in json_res and json_res['message'] != 'No message available':
                self.message += ' - {}'.format(json_res['message'])
            if 'code' in json_res:
                self.code = json_res['code']
            if 'data' in json_res:
                try:
                    self.message += " " + json.dumps(json_res['data'])
                except ValueError:
                    pass

        self.status_code = response.status_code
        self.response = response
        self.request = getattr(response, 'request', None)

    def __str__(self):  # pragma: no cover
        return 'KucoinAPIException {}: {}'.format(self.code, self.message)

class KucoinRequestException(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return 'KucoinRequestException: {}'.format(self.message)

class MarketOrderException(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return 'MarketOrderException: {}'.format(self.message)

class LimitOrderException(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return 'LimitOrderException: {}'.format(self.message)

def flat_uuid():
    """create a flat uuid
    :return: uuid with '-' removed
    """
    return str(uuid.uuid4()).replace('-', '')

def compact_json_dict(data):
    """convert dict to compact json
    :return: str
    """
    return json.dumps(data, separators=(',', ':'), ensure_ascii=False)

class Client(object):

    # REST_API_URL = 'https://openapi-v2.kucoin.com'
    REST_API_URL = ' https://api.kucoin.com'
    SANDBOX_API_URL = 'https://openapi-sandbox.kucoin.com'
    API_VERSION = 'v1'

    SIDE_BUY = 'buy'
    SIDE_SELL = 'sell'

    ACCOUNT_MAIN = 'main'
    ACCOUNT_TRADE = 'trade'

    ORDER_LIMIT = 'limit'
    ORDER_MARKET = 'market'
    ORDER_LIMIT_STOP = 'limit_stop'
    ORDER_MARKET_STOP = 'market_stop'

    STOP_LOSS = 'loss'
    STOP_ENTRY = 'entry'

    STP_CANCEL_NEWEST = 'CN'
    STP_CANCEL_OLDEST = 'CO'
    STP_DECREASE_AND_CANCEL = 'DC'
    STP_CANCEL_BOTH = 'CB'

    TIMEINFORCE_GOOD_TILL_CANCELLED = 'GTC'
    TIMEINFORCE_GOOD_TILL_TIME = 'GTT'
    TIMEINFORCE_IMMEDIATE_OR_CANCEL = 'IOC'
    TIMEINFORCE_FILL_OR_KILL = 'FOK'

    def __init__(self, api_key, api_secret, passphrase, sandbox=False, requests_params=None):
        """Kucoin API Client constructor
        https://docs.kucoin.com/
        :param api_key: Api Token Id
        :type api_key: string
        :param api_secret: Api Secret
        :type api_secret: string
        :param passphrase: Api Passphrase used to create API
        :type passphrase: string
        :param sandbox: (optional) Use the sandbox endpoint or not (default False)
        :type sandbox: bool
        :param requests_params: (optional) Dictionary of requests params to use for all calls
        :type requests_params: dict.
        .. code:: python
            client = Client(api_key, api_secret, api_passphrase)
        """

        self.API_KEY = api_key
        self.API_SECRET = api_secret
        self.API_PASSPHRASE = passphrase
        if sandbox:
            self.API_URL = self.SANDBOX_API_URL
        else:
            self.API_URL = self.REST_API_URL

        self._requests_params = requests_params
        self.session = self._init_session()

    def _init_session(self):

        session = requests.session()
        headers = {'Accept': 'application/json',
                   'User-Agent': 'python-kucoin',
                   'Content-Type': 'application/json',
                   'KC-API-KEY': self.API_KEY,
                   'KC-API-PASSPHRASE': self.API_PASSPHRASE}
        session.headers.update(headers)
        return session

    @staticmethod
    def _get_params_for_sig(data):
        """Convert params to ordered string for signature
        :param data:
        :return: ordered parameters like amount=10&price=1.1&type=BUY
        """
        return '&'.join(["{}={}".format(key, data[key]) for key in data])

    def _generate_signature(self, nonce, method, path, data):
        """Generate the call signature
        :param path:
        :param data:
        :param nonce:
        :return: signature string
        """

        data_json = ""
        endpoint = path
        if method == "get":
            if data:
                query_string = self._get_params_for_sig(data)
                endpoint = "{}?{}".format(path, query_string)
        elif data:
            data_json = compact_json_dict(data)
        sig_str = ("{}{}{}{}".format(nonce, method.upper(), endpoint, data_json)).encode('utf-8')
        m = hmac.new(self.API_SECRET.encode('utf-8'), sig_str, hashlib.sha256)
        return base64.b64encode(m.digest())

    def _create_path(self, path):
        return '/api/{}/{}'.format(self.API_VERSION, path)

    def _create_uri(self, path):
        return '{}{}'.format(self.API_URL, path)

    def _request(self, method, path, signed, **kwargs):

        # set default requests timeout
        kwargs['timeout'] = 100

        # add our global requests params
        if self._requests_params:
            kwargs.update(self._requests_params)

        kwargs['data'] = kwargs.get('data', {})
        kwargs['headers'] = kwargs.get('headers', {})

        full_path = self._create_path(path)
        uri = self._create_uri(full_path)

        if signed:
            # generate signature
            nonce = int(time.time() * 1000)
            kwargs['headers']['KC-API-TIMESTAMP'] = str(nonce)
            kwargs['headers']['KC-API-SIGN'] = self._generate_signature(nonce, method, full_path, kwargs['data'])

        if kwargs['data'] and method == 'get':
            kwargs['params'] = kwargs['data']
            del(kwargs['data'])

        if signed and method != 'get' and kwargs['data']:
            kwargs['data'] = compact_json_dict(kwargs['data'])

        response = getattr(self.session, method)(uri, **kwargs)
        return self._handle_response(response)

    @staticmethod
    def _handle_response(response):
        """Internal helper for handling API responses from the Quoine server.
        Raises the appropriate exceptions when necessary; otherwise, returns the
        response.
        """

        if not str(response.status_code).startswith('2'):
            raise KucoinAPIException(response)
        try:
            res = response.json()

            if 'code' in res and res['code'] != "200000":
                raise KucoinAPIException(response)

            if 'success' in res and not res['success']:
                raise KucoinAPIException(response)

            # by default return full response
            # if it's a normal response we have a data attribute, return that
            if 'data' in res:
                res = res['data']
            return res
        except ValueError:
            raise KucoinRequestException('Invalid Response: %s' % response.text)

    def _get(self, path, signed=False, **kwargs):
        return self._request('get', path, signed, **kwargs)

    def _post(self, path, signed=False, **kwargs):
        return self._request('post', path, signed, **kwargs)

    def _put(self, path, signed=False, **kwargs):
        return self._request('put', path, signed, **kwargs)

    def _delete(self, path, signed=False, **kwargs):
        return self._request('delete', path, signed, **kwargs)

    def get_timestamp(self):
        """Get the server timestamp
        https://docs.kucoin.com/#time
        :return: response timestamp in ms
        """
        return self._get("timestamp")

    # Currency Endpoints
    def get_symbols(self):
        """
            [
                {
                    "symbol": "BTC-USDT",
                    "name": "BTC-USDT",
                    "baseCurrency": "BTC",
                    "quoteCurrency": "USDT",
                    "baseMinSize": "0.00000001",
                    "quoteMinSize": "0.01",
                    "baseMaxSize": "10000",
                    "quoteMaxSize": "100000",
                    "baseIncrement": "0.00000001",
                    "quoteIncrement": "0.01",
                    "priceIncrement": "0.00000001",
                    "enableTrading": true
                }
            ]

        :raises: KucoinResponseException, KucoinAPIException

        """

        return self._get('symbols', False)

    def get_currency(self, currency):
        """Get single currency detail
        https://docs.kucoin.com/#get-currency-detail
        .. code:: python
            # call with no coins
            currency = client.get_currency('BTC')
        :returns: API Response
        .. code-block:: python
            {
                "currency": "BTC",
                "name": "BTC",
                "fullName": "Bitcoin",
                "precision": 8,
                "withdrawalMinSize": "0.002",
                "withdrawalMinFee": "0.0005",
                "isWithdrawEnabled": true,
                "isDepositEnabled": true
            }
        :raises:  KucoinResponseException, KucoinAPIException
        """

        return self._get('currencies/{}'.format(currency), False)

    # User Account Endpoints

    def get_accounts(self):
        """Get a list of accounts
        https://docs.kucoin.com/#accounts
        .. code:: python
            accounts = client.get_accounts()
        :returns: API Response
        .. code-block:: python
            [
                {
                    "id": "5bd6e9286d99522a52e458de",
                    "currency": "BTC",
                    "type": "main",
                    "balance": "237582.04299",
                    "available": "237582.032",
                    "holds": "0.01099"
                },
                {
                    "id": "5bd6e9216d99522a52e458d6",
                    "currency": "BTC",
                    "type": "trade",
                    "balance": "1234356",
                    "available": "1234356",
                    "holds": "0"
                }
            ]
        :raises:  KucoinResponseException, KucoinAPIException
        """

        return self._get('accounts', True)


    # Order Endpoints

    def create_market_order(self, symbol, side, tradeType='MARGIN_TRADE', size=None, funds=None, client_oid=None, remark=None, stp=None):
        """Create a market order
        One of size or funds must be set
        https://docs.kucoin.com/#place-a-new-order
        :param symbol: Name of symbol e.g. KCS-BTC
        :type symbol: string
        :param side: buy or sell
        :type side: string
        :param size: (optional) Desired amount in base currency
        :type size: string
        :param funds: (optional) Desired amount of quote currency to use
        :type funds: string
        :param client_oid: (optional) Unique order id (default flat_uuid())
        :type client_oid: string
        :param remark: (optional) remark for the order, max 100 utf8 characters
        :type remark: string
        :param stp: (optional) self trade protection CN, CO, CB or DC (default is None)
        :type stp: string
        .. code:: python
            order = client.create_market_order('NEO', Client.SIDE_BUY, size=20)
        :returns: ApiResponse
        .. code:: python
            {
                "orderOid": "596186ad07015679730ffa02"
            }
        :raises: KucoinResponseException, KucoinAPIException, MarketOrderException
        """

        if not size and not funds:
            raise MarketOrderException('Need size or fund parameter')

        if size and funds:
            raise MarketOrderException('Need size or fund parameter not both')

        data = {
            'side': side,
            'symbol': symbol,
            'type': self.ORDER_MARKET,
            'tradeType' : 'MARGIN_TRADE'
        }

        if size:
            data['size'] = size
        if funds:
            data['funds'] = funds
        if client_oid:
            data['clientOid'] = client_oid
        else:
            data['clientOid'] = flat_uuid()
        if remark:
            data['remark'] = remark
        if stp:
            data['stp'] = stp

        return self._post('orders', True, data=data)

    def create_limit_order(self, symbol, side, price, size, client_oid=None, remark=None,
                           time_in_force=None, stop=None, stop_price=None, stp=None, cancel_after=None, post_only=None,
                           hidden=None, iceberg=None, visible_size=None):
        """Create an order
        https://docs.kucoin.com/#place-a-new-order
        :param symbol: Name of symbol e.g. KCS-BTC
        :type symbol: string
        :param side: buy or sell
        :type side: string
        :param price: Name of coin
        :type price: string
        :param size: Amount of base currency to buy or sell
        :type size: string
        :param client_oid: (optional) Unique order_id  default flat_uuid()
        :type client_oid: string
        :param remark: (optional) remark for the order, max 100 utf8 characters
        :type remark: string
        :param stp: (optional) self trade protection CN, CO, CB or DC (default is None)
        :type stp: string
        :param time_in_force: (optional) GTC, GTT, IOC, or FOK (default is GTC)
        :type time_in_force: string
        :param stop: (optional) stop type loss or entry - requires stop_price
        :type stop: string
        :param stop_price: (optional) trigger price for stop order
        :type stop_price: string
        :param cancel_after: (optional) number of seconds to cancel the order if not filled
            required time_in_force to be GTT
        :type cancel_after: string
        :param post_only: (optional) indicates that the order should only make liquidity. If any part of
            the order results in taking liquidity, the order will be rejected and no part of it will execute.
        :type post_only: bool
        :param hidden: (optional) Orders not displayed in order book
        :type hidden: bool
        :param iceberg:  (optional) Only visible portion of the order is displayed in the order book
        :type iceberg: bool
        :param visible_size: (optional) The maximum visible size of an iceberg order
        :type visible_size: bool
        .. code:: python
            order = client.create_limit_order('KCS-BTC', Client.SIDE_BUY, '0.01', '1000')
        :returns: ApiResponse
        .. code:: python
            {
                "orderOid": "596186ad07015679730ffa02"
            }
        :raises: KucoinResponseException, KucoinAPIException, LimitOrderException
        """

        if stop and not stop_price:
            raise LimitOrderException('Stop order needs stop_price')

        if stop_price and not stop:
            raise LimitOrderException('Stop order type required with stop_price')

        if cancel_after and time_in_force != self.TIMEINFORCE_GOOD_TILL_TIME:
            raise LimitOrderException('Cancel after only works with time_in_force = "GTT"')

        if hidden and iceberg:
            raise LimitOrderException('Order can be either "hidden" or "iceberg"')

        if iceberg and not visible_size:
            raise LimitOrderException('Iceberg order requires visible_size')

        data = {
            'symbol': symbol,
            'side': side,
            'type': self.ORDER_LIMIT,
            'price': price,
            'size': size,
            'tradeType' : 'MARGIN_TRADE'
        }

        if client_oid:
            data['clientOid'] = client_oid
        else:
            data['clientOid'] = flat_uuid()
        if remark:
            data['remark'] = remark
        if stp:
            data['stp'] = stp
        if time_in_force:
            data['timeInForce'] = time_in_force
        if cancel_after:
            data['cancelAfter'] = cancel_after
        if post_only:
            data['postOnly'] = post_only
        if stop:
            data['stop'] = stop
            data['stopPrice'] = stop_price
        if hidden:
            data['hidden'] = hidden
        if iceberg:
            data['iceberg'] = iceberg
            data['visible_size'] = visible_size

        return self._post('orders', True, data=data)

    def cancel_all_orders(self, symbol=None):
        """Cancel all orders
        https://docs.kucoin.com/#cancel-all-orders
        .. code:: python
            res = client.cancel_all_orders()
        :returns: ApiResponse
        .. code:: python
            {
                "cancelledOrderIds": [
                    "5bd6e9286d99522a52e458de"
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """
        data = {}
        if symbol is not None:
            data['symbol'] = symbol
        return self._delete('orders', True, data=data)

    def get_orders(self, tradeType='MARGIN_TRADE', symbol=None, status=None, side=None, order_type=None,
                   start=None, end=None, page=None, limit=None):
        """Get list of orders
        https://docs.kucoin.com/#list-orders
        :param symbol: (optional) Name of symbol e.g. KCS-BTC
        :type symbol: string
        :param status: (optional) Specify status active or done (default done)
        :type status: string
        :param side: (optional) buy or sell
        :type side: string
        :param order_type: (optional) limit, market, limit_stop or market_stop
        :type order_type: string
        :param start: (optional) Start time as unix timestamp
        :type start: string
        :param end: (optional) End time as unix timestamp
        :type end: string
        :param page: (optional) Page to fetch
        :type page: int
        :param limit: (optional) Number of orders
        :type limit: int
        .. code:: python
            orders = client.get_orders(symbol='KCS-BTC', status='active')
        :returns: ApiResponse
        .. code:: python
            {
                "currentPage": 1,
                "pageSize": 1,
                "totalNum": 153408,
                "totalPage": 153408,
                "items": [
                    {
                        "id": "5c35c02703aa673ceec2a168",
                        "symbol": "BTC-USDT",
                        "opType": "DEAL",
                        "type": "limit",
                        "side": "buy",
                        "price": "10",
                        "size": "2",
                        "funds": "0",
                        "dealFunds": "0.166",
                        "dealSize": "2",
                        "fee": "0",
                        "feeCurrency": "USDT",
                        "stp": "",
                        "stop": "",
                        "stopTriggered": false,
                        "stopPrice": "0",
                        "timeInForce": "GTC",
                        "postOnly": false,
                        "hidden": false,
                        "iceberge": false,
                        "visibleSize": "0",
                        "cancelAfter": 0,
                        "channel": "IOS",
                        "clientOid": null,
                        "remark": null,
                        "tags": null,
                        "isActive": false,
                        "cancelExist": false,
                        "createdAt": 1547026471000
                    }
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {}
        data['tradeType'] = 'MARGIN_TRADE'
        if symbol:
            data['symbol'] = symbol
        if status:
            data['status'] = status
        if side:
            data['side'] = side
        if order_type:
            data['type'] = order_type
        if start:
            data['startAt'] = start
        if end:
            data['endAt'] = end
        if page:
            data['page'] = page
        if limit:
            data['pageSize'] = limit

        return self._get('orders', True, data=data)

    #Ticker Endpoints : get infos on a symbol

    def get_ticker(self, symbol=None):
        """Get symbol tick
        https://docs.kucoin.com/#get-ticker
        :param symbol: (optional) Name of symbol e.g. KCS-BTC
        :type symbol: string
        .. code:: python
            all_ticks = client.get_ticker()
            ticker = client.get_ticker('ETH-BTC')
        :returns: ApiResponse
        .. code:: python
            {
                "sequence": "1545825031840",      # now sequence
                "price": "3494.367783",           # last trade price
                "size": "0.05027185",             # last trade size
                "bestBid": "3494.367783",         # best bid price
                "bestBidSize": "2.60323254",      # size at best bid price
                "bestAsk": "3499.12",             # best ask price
                "bestAskSize": "0.01474011"       # size at best ask price
            }
        :raises: KucoinResponseException, KucoinAPIException
        """
        data = {}
        tick_path = 'market/allTickers'
        if symbol is not None:
            tick_path = 'market/orderbook/level1'
            data = {
                'symbol': symbol
            }
        return self._get(tick_path, False, data=data)

    #Kline Endpoints : get close prices of kandles
    def get_kline_data(self, symbol, kline_type='5min', start=None, end=None):
        """Get kline data
        For each query, the system would return at most 1500 pieces of data.
        To obtain more data, please page the data by time.
        :param symbol: Name of symbol e.g. KCS-BTC
        :type symbol: string
        :param kline_type: type of symbol, type of candlestick patterns: 1min, 3min, 5min, 15min, 30min, 1hour, 2hour,
                           4hour, 6hour, 8hour, 12hour, 1day, 1week
        :type kline_type: string
        :param start: Start time as unix timestamp (optional) default start of day in UTC
        :type start: int
        :param end: End time as unix timestamp (optional) default now in UTC
        :type end: int
        https://docs.kucoin.com/#get-historic-rates
        .. code:: python
            klines = client.get_kline_data('KCS-BTC', '5min', 1507479171, 1510278278)
        :returns: ApiResponse
        .. code:: python
            [
                [
                    "1545904980",             //Start time of the candle cycle
                    "0.058",                  //opening price
                    "0.049",                  //closing price
                    "0.058",                  //highest price
                    "0.049",                  //lowest price
                    "0.018",                  //Transaction amount
                    "0.000945"                //Transaction volume
                ],
                [
                    "1545904920",
                    "0.058",
                    "0.072",
                    "0.072",
                    "0.058",
                    "0.103",
                    "0.006986"
                ]
            ]
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'symbol': symbol
        }

        if kline_type is not None:
            data['type'] = kline_type
        if start is not None:
            data['startAt'] = start
        else:
            data['startAt'] = calendar.timegm(datetime.utcnow().date().timetuple())
        if end is not None:
            data['endAt'] = end
        else:
            data['endAt'] = int(time.time())

        return self._get('market/candles', False, data=data)


