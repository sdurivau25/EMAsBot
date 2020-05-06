# coding=utf-8

#Kucoin trading bot
# 1: Imports
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

# 2 : System error codes
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

# 3: Kucoin APIs links
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

    REST_API_URL = 'https://openapi-v2.kucoin.com'
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
        kwargs['timeout'] = 10

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

    def get_currencies(self):
        """List known currencies
        https://docs.kucoin.com/#get-currencies
        .. code:: python
            currencies = client.get_currencies()
        :returns: API Response
        .. code-block:: python
            [
                {
                    "currency": "BTC",
                    "name": "BTC",
                    "fullName": "Bitcoin",
                    "precision": 8
                },
                {
                    "currency": "ETH",
                    "name": "ETH",
                    "fullName": "Ethereum",
                    "precision": 7
                }
            ]
        :raises:  KucoinResponseException, KucoinAPIException
        """

        return self._get('currencies', False)

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

    def get_account(self, account_id):
        """Get an individual account
        https://docs.kucoin.com/#get-an-account
        :param account_id: ID for account - from list_accounts()
        :type account_id: string
        .. code:: python
            account = client.get_account('5bd6e9216d99522a52e458d6')
        :returns: API Response
        .. code-block:: python
            {
                "currency": "KCS",
                "balance": "1000000060.6299",
                "available": "1000000060.6299",
                "holds": "0"
            }
        :raises:  KucoinResponseException, KucoinAPIException
        """

        return self._get('accounts/{}'.format(account_id), True)

    def create_account(self, account_type, currency):
        """Create an account
        https://docs.kucoin.com/#create-an-account
        :param account_type: Account type - main or trade
        :type account_type: string
        :param currency: Currency code
        :type currency: string
        .. code:: python
            account = client.create_account('trade', 'BTC')
        :returns: API Response
        .. code-block:: python
            {
                "id": "5bd6e9286d99522a52e458de"
            }
        :raises:  KucoinResponseException, KucoinAPIException
        """

        data = {
            'type': account_type,
            'currency': currency
        }

        return self._post('accounts', True, data=data)

    def get_account_activity(self, account_id, start=None, end=None, page=None, limit=None):
        """Get list of account activity
        https://docs.kucoin.com/#get-account-history
        :param account_id: ID for account - from list_accounts()
        :type account_id: string
        :param start: (optional) Start time as unix timestamp
        :type start: string
        :param end: (optional) End time as unix timestamp
        :type end: string
        :param page: (optional) Current page - default 1
        :type page: int
        :param limit: (optional) Number of results to return - default 50
        :type limit: int
        .. code:: python
            history = client.get_account_activity('5bd6e9216d99522a52e458d6')
            history = client.get_account_activity('5bd6e9216d99522a52e458d6', start='1540296039000')
            history = client.get_account_activity('5bd6e9216d99522a52e458d6', page=2, page_size=10)
        :returns: API Response
        .. code-block:: python
            {
                "currentPage": 1,
                "pageSize": 10,
                "totalNum": 2,
                "totalPage": 1,
                "items": [
                    {
                        "currency": "KCS",
                        "amount": "0.0998",
                        "fee": "0",
                        "balance": "1994.040596",
                        "bizType": "withdraw",
                        "direction": "in",
                        "createdAt": 1540296039000,
                        "context": {
                             "orderId": "5bc7f080b39c5c03286eef8a",
                             "currency": "BTC"
                         }
                    },
                    {
                        "currency": "KCS",
                        "amount": "0.0998",
                        "fee": "0",
                        "balance": "1994.140396",
                        "bizType": "trade exchange",
                        "direction": "in",
                        "createdAt": 1540296039000,
                        "context": {
                             "orderId": "5bc7f080b39c5c03286eef8e",
                             "tradeId": "5bc7f080b3949c03286eef8a",
                             "symbol": "BTC-USD"
                        }
                    }
                ]
            }
        :raises:  KucoinResponseException, KucoinAPIException
        """

        data = {}
        if start:
            data['startAt'] = start
        if end:
            data['endAt'] = end
        if page:
            data['currentPage'] = page
        if limit:
            data['pageSize'] = limit

        return self._get('accounts/{}/ledgers'.format(account_id), True, data=data)

    def get_account_holds(self, account_id, page=None, page_size=None):
        """Get account holds placed for any active orders or pending withdraw requests
        https://docs.kucoin.com/#get-holds
        :param account_id: ID for account - from list_accounts()
        :type account_id: string
        :param page: (optional) Current page - default 1
        :type page: int
        :param page_size: (optional) Number of results to return - default 50
        :type page_size: int
        .. code:: python
            holds = client.get_account_holds('5bd6e9216d99522a52e458d6')
            holds = client.get_account_holds('5bd6e9216d99522a52e458d6', page=2, page_size=10)
        :returns: API Response
        .. code-block:: python
            {
                "currentPage": 1,
                "pageSize": 10,
                "totalNum": 2,
                "totalPage": 1,
                "items": [
                    {
                        "currency": "ETH",
                        "holdAmount": "5083",
                        "bizType": "Withdraw",
                        "orderId": "5bc7f080b39c5c03286eef8e",
                        "createdAt": 1545898567000,
                        "updatedAt": 1545898567000
                    },
                    {
                        "currency": "ETH",
                        "holdAmount": "1452",
                        "bizType": "Withdraw",
                        "orderId": "5bc7f518b39c5c033818d62d",
                        "createdAt": 1545898567000,
                        "updatedAt": 1545898567000
                    }
                ]
            }
        :raises:  KucoinResponseException, KucoinAPIException
        """

        data = {}
        if page:
            data['currentPage'] = page
        if page_size:
            data['pageSize'] = page_size

        return self._get('accounts/{}/holds'.format(account_id), True, data=data)

    def create_inner_transfer(self, from_account_id, to_account_id, amount, order_id=None):
        """Get account holds placed for any active orders or pending withdraw requests
        https://docs.kucoin.com/#get-holds
        :param from_account_id: ID of account to transfer funds from - from list_accounts()
        :type from_account_id: str
        :param to_account_id: ID of account to transfer funds to - from list_accounts()
        :type to_account_id: str
        :param amount: Amount to transfer
        :type amount: int
        :param order_id: (optional) Request ID (default flat_uuid())
        :type order_id: string
        .. code:: python
            transfer = client.create_inner_transfer('5bd6e9216d99522a52e458d6', 5bc7f080b39c5c03286eef8e', 20)
        :returns: API Response
        .. code-block:: python
            {
                "orderId": "5bd6e9286d99522a52e458de"
            }
        :raises:  KucoinResponseException, KucoinAPIException
        """

        data = {
            'payAccountId': from_account_id,
            'recAccountId': to_account_id,
            'amount': amount
        }

        if order_id:
            data['clientOid'] = order_id
        else:
            data['clientOid'] = flat_uuid()

        return self._post('accounts/inner-transfer', True, data=data)

    # Deposit Endpoints

    def create_deposit_address(self, currency):
        """Create deposit address of currency for deposit. You can just create one deposit address.
        https://docs.kucoin.com/#create-deposit-address
        :param currency: Name of currency
        :type currency: string
        .. code:: python
            address = client.create_deposit_address('NEO')
        :returns: ApiResponse
        .. code:: python
            {
                "address": "0x78d3ad1c0aa1bf068e19c94a2d7b16c9c0fcd8b1",
                "memo": "5c247c8a03aa677cea2a251d"
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'currency': currency
        }

        return self._post('deposit-addresses', True, data=data)

    def get_deposit_address(self, currency):
        """Get deposit address for a currency
        https://docs.kucoin.com/#get-deposit-address
        :param currency: Name of currency
        :type currency: string
        .. code:: python
            address = client.get_deposit_address('NEO')
        :returns: ApiResponse
        .. code:: python
            {
                "address": "0x78d3ad1c0aa1bf068e19c94a2d7b16c9c0fcd8b1",
                "memo": "5c247c8a03aa677cea2a251d"
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'currency': currency
        }

        return self._get('deposit-addresses', True, data=data)

    def get_deposits(self, currency=None, status=None, start=None, end=None, page=None, limit=None):
        """Get deposit records for a currency
        https://docs.kucoin.com/#get-deposit-list
        :param currency: Name of currency (optional)
        :type currency: string
        :param status: optional - Status of deposit (PROCESSING, SUCCESS, FAILURE)
        :type status: string
        :param start: (optional) Start time as unix timestamp
        :type start: string
        :param end: (optional) End time as unix timestamp
        :type end: string
        :param page: (optional) Page to fetch
        :type page: int
        :param limit: (optional) Number of transactions
        :type limit: int
        .. code:: python
            deposits = client.get_deposits('NEO')
        :returns: ApiResponse
        .. code:: python
            {
                "currentPage": 1,
                "pageSize": 5,
                "totalNum": 2,
                "totalPage": 1,
                "items": [
                    {
                        "address": "0x5f047b29041bcfdbf0e4478cdfa753a336ba6989",
                        "memo": "5c247c8a03aa677cea2a251d",
                        "amount": 1,
                        "fee": 0.0001,
                        "currency": "KCS",
                        "isInner": false,
                        "walletTxId": "5bbb57386d99522d9f954c5a@test004",
                        "status": "SUCCESS",
                        "createdAt": 1544178843000,
                        "updatedAt": 1544178891000
                    }, {
                        "address": "0x5f047b29041bcfdbf0e4478cdfa753a336ba6989",
                        "memo": "5c247c8a03aa677cea2a251d",
                        "amount": 1,
                        "fee": 0.0001,
                        "currency": "KCS",
                        "isInner": false,
                        "walletTxId": "5bbb57386d99522d9f954c5a@test003",
                        "status": "SUCCESS",
                        "createdAt": 1544177654000,
                        "updatedAt": 1544178733000
                    }
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {}
        if currency:
            data['currency'] = currency
        if status:
            data['status'] = status
        if start:
            data['startAt'] = start
        if end:
            data['endAt'] = end
        if limit:
            data['pageSize'] = limit
        if page:
            data['page'] = page

        return self._get('deposits', True, data=data)

    # Withdraw Endpoints

    def get_withdrawals(self, currency=None, status=None, start=None, end=None, page=None, limit=None):
        """Get deposit records for a currency
        https://docs.kucoin.com/#get-withdrawals-list
        :param currency: Name of currency (optional)
        :type currency: string
        :param status: optional - Status of deposit (PROCESSING, SUCCESS, FAILURE)
        :type status: string
        :param start: (optional) Start time as unix timestamp
        :type start: string
        :param end: (optional) End time as unix timestamp
        :type end: string
        :param page: (optional) Page to fetch
        :type page: int
        :param limit: (optional) Number of transactions
        :type limit: int
        .. code:: python
            withdrawals = client.get_withdrawals('NEO')
        :returns: ApiResponse
        .. code:: python
            {
                "currentPage": 1,
                "pageSize": 10,
                "totalNum": 1,
                "totalPage": 1,
                "items": [
                    {
                        "id": "5c2dc64e03aa675aa263f1ac",
                        "address": "0x5bedb060b8eb8d823e2414d82acce78d38be7fe9",
                        "memo": "",
                        "currency": "ETH",
                        "amount": 1.0000000,
                        "fee": 0.0100000,
                        "walletTxId": "3e2414d82acce78d38be7fe9",
                        "isInner": false,
                        "status": "FAILURE",
                        "createdAt": 1546503758000,
                        "updatedAt": 1546504603000
                    }
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {}
        if currency:
            data['currency'] = currency
        if status:
            data['status'] = status
        if start:
            data['startAt'] = start
        if end:
            data['endAt'] = end
        if limit:
            data['pageSize'] = limit
        if page:
            data['page'] = page

        return self._get('withdrawals', True, data=data)

    def get_withdrawal_quotas(self, currency):
        """Get withdrawal quotas for a currency
        https://docs.kucoin.com/#get-withdrawal-quotas
        :param currency: Name of currency
        :type currency: string
        .. code:: python
            quotas = client.get_withdrawal_quotas('ETH')
        :returns: ApiResponse
        .. code:: python
            {
                "currency": "ETH",
                "availableAmount": 2.9719999,
                "remainAmount": 2.9719999,
                "withdrawMinSize": 0.1000000,
                "limitBTCAmount": 2.0,
                "innerWithdrawMinFee": 0.00001,
                "isWithdrawEnabled": true,
                "withdrawMinFee": 0.0100000,
                "precision": 7
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'currency': currency
        }

        return self._get('withdrawals/quotas', True, data=data)

    def create_withdrawal(self, currency, amount, address, memo=None, is_inner=False, remark=None):
        """Process a withdrawal
        https://docs.kucoin.com/#apply-withdraw
        :param currency: Name of currency
        :type currency: string
        :param amount: Amount to withdraw
        :type amount: number
        :param address: Address to withdraw to
        :type address: string
        :param memo: (optional) Remark to the withdrawal address
        :type memo: string
        :param is_inner: (optional) Remark to the withdrawal address
        :type is_inner: bool
        :param remark: (optional) Remark
        :type remark: string
        .. code:: python
            withdrawal = client.create_withdrawal('NEO', 20, '598aeb627da3355fa3e851')
        :returns: ApiResponse
        .. code:: python
            {
                "withdrawalId": "5bffb63303aa675e8bbe18f9"
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'currency': currency,
            'amount': amount,
            'address': address
        }

        if memo:
            data['memo'] = memo
        if is_inner:
            data['isInner'] = is_inner
        if remark:
            data['remark'] = remark

        return self._post('withdrawals', True, data=data)

    def cancel_withdrawal(self, withdrawal_id):
        """Cancel a withdrawal
        https://docs.kucoin.com/#cancel-withdrawal
        :param withdrawal_id: ID of withdrawal
        :type withdrawal_id: string
        .. code:: python
            client.cancel_withdrawal('5bffb63303aa675e8bbe18f9')
        :returns: None
        :raises: KucoinResponseException, KucoinAPIException
        """

        return self._delete('withdrawals/{}'.format(withdrawal_id), True)

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

    def cancel_order(self, order_id):
        """Cancel an order
        https://docs.kucoin.com/#cancel-an-order
        :param order_id: Order id
        :type order_id: string
        .. code:: python
            res = client.cancel_order('5bd6e9286d99522a52e458de)
        :returns: ApiResponse
        .. code:: python
            {
                "cancelledOrderIds": [
                    "5bd6e9286d99522a52e458de"
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        KucoinAPIException If order_id is not found
        """

        return self._delete('orders/{}'.format(order_id), True)

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

    def get_historical_orders(self, symbol=None, side=None,
                              start=None, end=None, page=None, limit=None):
        """List of KuCoin V1 historical orders.
        https://docs.kucoin.com/#get-v1-historical-orders-list
        :param symbol: (optional) Name of symbol e.g. KCS-BTC
        :type symbol: string
        :param side: (optional) buy or sell
        :type side: string
        :param start: (optional) Start time as unix timestamp
        :type start: string
        :param end: (optional) End time as unix timestamp
        :type end: string
        :param page: (optional) Page to fetch
        :type page: int
        :param limit: (optional) Number of orders
        :type limit: int
        .. code:: python
            orders = client.get_historical_orders(symbol='KCS-BTC')
        :returns: ApiResponse
        .. code:: python
            {
                "currentPage": 1,
                "pageSize": 50,
                "totalNum": 1,
                "totalPage": 1,
                "items": [
                    {
                        "symbol": "SNOV-ETH",
                        "dealPrice": "0.0000246",
                        "dealValue": "0.018942",
                        "amount": "770",
                        "fee": "0.00001137",
                        "side": "sell",
                        "createdAt": 1540080199
                    }
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {}

        if symbol:
            data['symbol'] = symbol
        if side:
            data['side'] = side
        if start:
            data['startAt'] = start
        if end:
            data['endAt'] = end
        if page:
            data['page'] = page
        if limit:
            data['pageSize'] = limit

        return self._get('hist-orders', True, data=data)

    def get_order(self, order_id):
        """Get order details
        https://docs.kucoin.com/#get-an-order
        :param order_id: orderOid value
        :type order_id: str
        .. code:: python
            order = client.get_order('5c35c02703aa673ceec2a168')
        :returns: ApiResponse
        .. code:: python
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
        :raises: KucoinResponseException, KucoinAPIException
        """

        return self._get('orders/{}'.format(order_id), True)

    # Fill Endpoints

    def get_fills(self, order_id=None, symbol=None, side=None, order_type=None,
                  start=None, end=None, page=None, limit=None):
        """Get a list of recent fills.
        https://docs.kucoin.com/#list-fills
        :param order_id: (optional) generated order id
        :type order_id: string
        :param symbol: (optional) Name of symbol e.g. KCS-BTC
        :type symbol: string
        :param side: (optional) buy or sell
        :type side: string
        :param order_type: (optional) limit, market, limit_stop or market_stop
        :type order_type: string
        :param start: Start time as unix timestamp (optional)
        :type start: string
        :param end: End time as unix timestamp (optional)
        :type end: string
        :param page: optional - Page to fetch
        :type page: int
        :param limit: optional - Number of orders
        :type limit: int
        .. code:: python
            fills = client.get_fills()
        :returns: ApiResponse
        .. code:: python
            {
                "currentPage":1,
                "pageSize":1,
                "totalNum":251915,
                "totalPage":251915,
                "items":[
                    {
                        "symbol":"BTC-USDT",
                        "tradeId":"5c35c02709e4f67d5266954e",
                        "orderId":"5c35c02703aa673ceec2a168",
                        "counterOrderId":"5c1ab46003aa676e487fa8e3",
                        "side":"buy",
                        "liquidity":"taker",
                        "forceTaker":true,
                        "price":"0.083",
                        "size":"0.8424304",
                        "funds":"0.0699217232",
                        "fee":"0",
                        "feeRate":"0",
                        "feeCurrency":"USDT",
                        "stop":"",
                        "type":"limit",
                        "createdAt":1547026472000
                    }
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {}
        data['tradeType'] = 'MARGIN_TRADE'
        if order_id:
            data['orderId'] = order_id
        if symbol:
            data['symbol'] = symbol
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

        return self._get('fills', True, data=data)

    # Market Endpoints

    def get_symbols(self):
        """Get a list of available currency paires for trading.
        https://docs.kucoin.com/#symbols-amp-ticker
        .. code:: python
            symbols = client.get_symbols()
        :returns: ApiResponse
        .. code:: python
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

    def get_fiat_prices(self, base=None, symbol=None):
        """Get fiat price for currency
        https://docs.kucoin.com/#get-fiat-price
        :param base: (optional) Fiat,eg.USD,EUR, default is USD.
        :type base: string
        :param symbol: (optional) Cryptocurrencies.For multiple cyrptocurrencies, please separate them with
                       comma one by one. default is all
        :type symbol: string
        .. code:: python
            prices = client.get_fiat_prices()
        :returns: ApiResponse
        .. code:: python
            {
                "BTC": "3911.28000000",
                "ETH": "144.55492453",
                "LTC": "48.45888179",
                "KCS": "0.45546856"
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {}

        if base is not None:
            data['base'] = base
        if symbol is not None:
            data['currencies'] = symbol

        return self._get('prices', False, data=data)

    def get_24hr_stats(self, symbol):
        """Get 24hr stats for a symbol. Volume is in base currency units. open, high, low are in quote currency units.
        :param symbol: (optional) Name of symbol e.g. KCS-BTC
        :type symbol: string
        .. code:: python
            stats = client.get_24hr_stats('ETH-BTC')
        :returns: ApiResponse
        Without a symbol param
        .. code:: python
            {
                "symbol": "BTC-USDT",
                "changeRate": "0.0128",   # 24h change rate
                "changePrice": "0.8",     # 24h rises and falls in price (if the change rate is a negative number,
                                          # the price rises; if the change rate is a positive number, the price falls.)
                "open": 61,               # Opening price
                "close": 63.6,            # Closing price
                "high": "63.6",           # Highest price filled
                "low": "61",              # Lowest price filled
                "vol": "244.78",          # Transaction quantity
                "volValue": "15252.0127"  # Transaction amount
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'symbol': symbol
        }

        return self._get('market/stats', False, data=data)

    def get_markets(self):
        """Get supported market list
        https://docs.kucoin.com/#get-market-list
        .. code:: python
            markets = client.get_markets()
        :returns: ApiResponse
        .. code:: python
            {
                "data": [
                    "BTC",
                    "ETH",
                    "USDT"
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """
        return self._get('markets', False)

    def get_order_book(self, symbol):
        """Get a list of bids and asks aggregated by price for a symbol.
        Returns up to 100 depth each side. Fastest Order book API
        https://docs.kucoin.com/#get-part-order-book-aggregated
        :param symbol: Name of symbol e.g. KCS-BTC
        :type symbol: string
        .. code:: python
            orders = client.get_order_book('KCS-BTC')
        :returns: ApiResponse
        .. code:: python
            {
                "sequence": "3262786978",
                "bids": [
                    ["6500.12", "0.45054140"],  # [price, size]
                    ["6500.11", "0.45054140"]
                ],
                "asks": [
                    ["6500.16", "0.57753524"],
                    ["6500.15", "0.57753524"]
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'symbol': symbol
        }

        return self._get('market/orderbook/level2_100', False, data=data)

    def get_full_order_book(self, symbol):
        """Get a list of all bids and asks aggregated by price for a symbol.
        This call is generally used by professional traders because it uses more server resources and traffic,
        and Kucoin has strict access frequency control.
        https://docs.kucoin.com/#get-full-order-book-aggregated
        :param symbol: Name of symbol e.g. KCS-BTC
        :type symbol: string
        .. code:: python
            orders = client.get_order_book('KCS-BTC')
        :returns: ApiResponse
        .. code:: python
            {
                "sequence": "3262786978",
                "bids": [
                    ["6500.12", "0.45054140"],  # [price size]
                    ["6500.11", "0.45054140"]
                ],
                "asks": [
                    ["6500.16", "0.57753524"],
                    ["6500.15", "0.57753524"]
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'symbol': symbol
        }

        return self._get('market/orderbook/level2', False, data=data)

    def get_full_order_book_level3(self, symbol):
        """Get a list of all bids and asks non-aggregated for a symbol.
        This call is generally used by professional traders because it uses more server resources and traffic,
        and Kucoin has strict access frequency control.
        https://docs.kucoin.com/#get-full-order-book-atomic
        :param symbol: Name of symbol e.g. KCS-BTC
        :type symbol: string
        .. code:: python
            orders = client.get_order_book('KCS-BTC')
        :returns: ApiResponse
        .. code:: python
            {
                "sequence": "1545896707028",
                "bids": [
                    [
                        "5c2477e503aa671a745c4057",   # orderId
                        "6",                          # price
                        "0.999"                       # size
                    ],
                    [
                        "5c2477e103aa671a745c4054",
                        "5",
                        "0.999"
                    ]
                ],
                "asks": [
                    [
                        "5c24736703aa671a745c401e",
                        "200",
                        "1"
                    ],
                    [
                        "5c2475c903aa671a745c4033",
                        "201",
                        "1"
                    ]
                ]
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'symbol': symbol
        }

        return self._get('market/orderbook/level3', False, data=data)

    def get_trade_histories(self, symbol):
        """List the latest trades for a symbol
        https://docs.kucoin.com/#get-trade-histories
        :param symbol: Name of symbol e.g. KCS-BTC
        :type symbol: string
        .. code:: python
            orders = client.get_trade_histories('KCS-BTC')
        :returns: ApiResponse
        .. code:: python
            [
                {
                    "sequence": "1545896668571",
                    "price": "0.07",                # Filled price
                    "size": "0.004",                # Filled amount
                    "side": "buy",                  # Filled side. The filled side is set to the taker by default.
                    "time": 1545904567062140823     # Transaction time
                },
                {
                    "sequence": "1545896668578",
                    "price": "0.054",
                    "size": "0.066",
                    "side": "buy",
                    "time": 1545904581619888405
                }
            ]
        :raises: KucoinResponseException, KucoinAPIException
        """

        data = {
            'symbol': symbol
        }

        return self._get('market/histories', False, data=data)

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

    # Websocket Endpoints

    def get_ws_endpoint(self, private=False):
        """Get websocket channel details
        :param private: Name of symbol e.g. KCS-BTC
        :type private: bool
        https://docs.kucoin.com/#websocket-feed
        .. code:: python
            ws_details = client.get_ws_endpoint(private=True)
        :returns: ApiResponse
        .. code:: python
            {
                "code": "200000",
                "data": {
                    "instanceServers": [
                        {
                            "pingInterval": 50000,
                            "endpoint": "wss://push1-v2.kucoin.net/endpoint",
                            "protocol": "websocket",
                            "encrypt": true,
                            "pingTimeout": 10000
                        }
                    ],
                    "token": "vYNlCtbz4XNJ1QncwWilJnBtmmfe4geLQDUA62kKJsDChc6I4bRDQc73JfIrlFaVYIAE0Gv2--MROnLAgjVsWkcDq_MuG7qV7EktfCEIphiqnlfpQn4Ybg==.IoORVxR2LmKV7_maOR9xOg=="
                }
            }
        :raises: KucoinResponseException, KucoinAPIException
        """

        path = 'bullet-public'
        signed = private
        if private:
            path = 'bullet-private'

        return self._post(path, signed)


#Fonctions :
def log_func(msg):
    with open('log.txt','a') as f:
        f.write('{}\n'.format(msg))
        
def read_log():
    with open('log.txt','r') as f:
        txt=f.read()
    return txt
        
def round_to_6_decimal(x):
    return float(int(x*10**6)/10**6)
    
def round_to_5_decimal(x):
    return float(int(x*10**5)/10**5)
        
    
def telegram_bot_send(bot_message):
    bot_token = '1207437362:AAH6SW6NSLEQWT3nIG7C6NI4AQaZ1vYTUbg'
    self.bot_chatID = '950826450'
    send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + self.bot_chatID + '&parse_mode=Markdown&text=' + bot_message
    response = requests.get(send_text)
    return response.json()
    
# Initialisation
log_func('Initialisation...')
client0 = Client(input('Quelle est votre cle publique? : '),input('Quelle est votre cle privee? : '), input('Quelle est votre mot de passe ?'))
bot_token1 = input('@Trading_Notif_Bot token ?')
bot_token2 = input('@LogsBot token ?')
log_func('Connecte')

#Indicators calculus :
class Indicators(Thread):
    """Indicators from Kucoin's price"""
    
    def __init__(self, paire, client=client0):
        assert isinstance(client, Client)
        Thread.__init__(self)
        self.client = client0
        self.paire = paire
        self.get_2h_prices()
        self.calc_2h_emas()
        
    def get_2h_prices(self):
        self.prices = [float(x[2]) for x in client.get_kline_data(symbol=self.paire, kline_type='2hour', start=int(time.time() - 1879200))]   
            
    def calc_2h_emas(self):        
         #1 : calcul des sma qui serviront de première ema
        self.sma20=0.0
        for i in range(19,39):
            self.sma20 += self.prices[i]
        self.sma20 = self.sma20/20
        
        self.sma45=0.0
        for i in range(44,89):
            self.sma45 += self.prices[i]
        self.sma45 = self.sma45/45
        
        self.sma130=0.0
        for i in range(129,259):
            self.sma130 += self.prices[i]
        self.sma130 = self.sma130/130
         # 2 : Calcul des multiplicateurs
        self.m20 = 2/(20+1)
        self.m45= 2/(45+1)
        self.m130= 2/(130+1)
         # 3 : Calcul des ema
        self.ema20=self.sma20
        for i in range(1,20):
            self.ema20 = (self.prices[20-i]-self.ema20)*self.m20 + self.ema20
            
        self.ema45=self.sma45
        for i in range(1,45):
            self.ema45 = (self.prices[45-i]-self.ema45)*self.m45 + self.ema45
            
        self.ema130=self.sma130
        for i in range(1,130):
            self.ema130 = (self.prices[130-i]-self.ema130)*self.m130 + self.ema130

        def run(self):
            while True :
                self.get_2h_prices()
                self.calc_2h_emas()
                sleep(15)
                
    
    
#Bot
class Bot(Thread) :
    """EMA TradingBot for Kucoin"""

    def __init__(self, owner, client, bot_chatID1, base, quote, your_base, your_quote, margin_base, margin_quote, indicators, bypass=False) :
        Thread.__init__(self)
        self.owner = owner
        self.client = client
        self.bot_token = bot_token1
        self.bot_chatID = bot_chatID1
        self.base = base
        self.quote = quote
        self.paire = '{}-{}'.format(self.quote,self.base)
        self.indicators = indicators
        self.your_base = float(your_base)
        self.your_quote = float(your_quote)
        self.margin_base = float(margin_base)
        self.margin_quote = float(margin_quote)
        self.base_qty = float(your_base) + float(margin_base)
        self.quote_qty = float(self.your_quote)+float(self.margin_quote)
        self.min_base = float(self.client.get_currency(base)['withdrawalMinSize'])
        self.min_quote = float(self.client.get_currency(quote)['withdrawalMinSize'])
        self.bypass = bypass
        self.firstvalue = float(self.your_base)+float(self.your_quote)*float(self.client.get_ticker(self.paire)['price'])
        self.continuer=True
        self.paused = False
        self.last_telegram_id = requests.get('https://api.telegram.org/bot' + self.bot_token + '/getUpdates?chat_id=' + bot_chatID1).json()['result'][-1]['message']['date']

        
    def log(self, message:str):
        log_func(strftime('[%d/%m %H:%M:%S] Bot {} : {}'.format(id(self), message)))
        
    def wallet(self):
        self.firstvalue = self.firstvalue
        self.walletvalue1 = (float(self.base_qty)-float(self.margin_base))+(float(self.quote_qty) - float(self.margin_quote))*float(self.client.get_ticker(self.paire)['price'])
        self.walletvalue = round_to_5_decimal(self.walletvalue1)
        if self.firstvalue != 0.0:
            self.roi = (round_to_5_decimal(self.walletvalue1/self.firstvalue) - 1)*100
        else :
            self.roi = '0'
    
    def telegram_bot_sendtext(self, bot_message):
        self.bot_token = bot_token1
        self.send_text = 'https://api.telegram.org/bot' + self.bot_token + '/sendMessage?chat_id=' + self.bot_chatID + '&parse_mode=Markdown&text=' + bot_message
        self.response = requests.get(self.send_text)
        return self.response.json()
        
    def telegram_answer(self):
        self.get = 'https://api.telegram.org/bot' + self.bot_token + '/getUpdates?chat_id=' + self.bot_chatID
        self.response = requests.get(self.get)
        self.id = self.response.json()['result'][-1]['message']
        if self.id['date'] != self.last_telegram_id:
            self.wallet()
            self.ask=self.id['text']
            if self.ask == '/roi' :
                if self.roi != '0':
                    self.answer  = 'You made +{}% of profit'.format(self.roi)
                else :
                    self.answer = 'Your wallet is empty'
            elif self.ask == '/wallet' :
                self.answer = 'Your wallet is worth {} {}'.format(self.walletvalue, self.base)
            elif self.ask == '/credits':
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
            elif self.ask == '/commands' :
                self.answer = """Commands :
                /wallet : get your current wallet value, minus what you borrowed
                /roi : get your current Return On Investment
                /credits"""
            else :
                self.answer = 'Unknown command, type /commands to get commands'
            self.telegram_bot_sendtext(self.answer)
            self.last_telegram_id = self.id['date']
        
    def analyze_market(self):
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
        if self.full_long:
            if self.base_qty > self.min_base :
                self.buy_all=True
                self.order_size=0.99*(round_to_6_decimal(self.base_qty))
                self.log("Long, {}".format(self.paire))
            else :
                self.buy_all=False
        if self.full_short:
            if self.quote_qty > self.min_quote :
                self.sell_all=True
                self.order_size=0.99*round_to_6_decimal(self.quote_qty)
                self.log("Short, {}".format(self.paire))
            else :
                self.sell_all=False
        if self.stop_long :
            if self.quote_qty > self.margin_quote and (self.quote_qty-self.margin_quote)>self.min_quote:
                self.order_size=0.99*round_to_6_decimal(self.quote_qty-self.margin_quote)
                self.sell_long=True
                self.log("Stop long, {}".format(self.paire))
            else :
                self.sell_long=False
        if self.stop_short :
            if self.base_qty>self.margin_base and (self.base_qty-self.margin_base)>self.min_base:
                self.order_size=0.99*round_to_6_decimal(self.base_qty-self.margin_base)
                self.sell_short=True
                self.log("Stop short, {}".format(self.paire))
            else :
                self.sell_short=False          
            
    def place_order(self):
        if self.buy_all or self.sell_short :
            self.log('Gonna place a buy order')
            self.client.create_market_order(self.paire, Client.SIDE_BUY, funds=self.order_size)
            sleep(1.5)
            self.lastorder = self.client.get_orders(symbol=self.paire)['items'][0]
            self.telegram_bot_sendtext('Hey {} , I bought {}{} at price {}, using {}{}'.format(self.owner, self.lastorder['dealSize'],self.quote, self.lastorder['price'], self.lastorder['dealFunds'], self.base))
            self.log('{} bought {}{} at price {}, using {}{}'.format(self.owner, self.lastorder['dealSize'],self.quote, self.lastorder['price'], self.lastorder['dealFunds'], self.base))
        elif self.sell_all or self.sell_long :
            self.log('Gonna place a sell order')
            self.client.create_market_order(self.paire, Client.SIDE_SELL, size=self.order_size)
            sleep(1.5)
            self.lastorder = self.client.get_orders(symbol=self.paire)['items'][0]
            self.telegram_bot_sendtext('Hey {} , I sold {}{} at price {}, winning {}{}'.format(self.lastorder['dealSize'],self.quote, self.lastorder['price'], self.lastorder['dealFunds'], self.base))
            self.log('{} sold {}{} at price {}, winning {}{}'.format(self.owner, self.lastorder['dealSize'],self.quote, self.lastorder['price'], self.lastorder['dealFunds'], self.base))
            
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
            self.quote_qty = float(self.quote_qty)-float(self.lastorder[0]['dealSize'])
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
            while self.continuer:
                
                sleep(2.0)
                while self.paused:
                
                    sleep(10)
                self.analyze_market()
                self.check_to_do()
                self.place_order()
                self.conclude()
            self.log('Opérations terminées, bot en veille...')
        elif self.full_long :
            while self.full_long :
                
                sleep(10)
                self.analyze_market()
            self.log('Bot found its entry point')
            self.telegram_bot_sendtext('Bot found its entry point')
            self.log('Bot is ready...')
            while self.continuer:
                
                sleep(2.0)
                while self.paused:
                    sleep(10)
                self.analyze_market()
                self.check_to_do()
                self.place_order()
                self.conclude()
            self.log('Opérations terminées, bot en veille...')
        elif self.full_short :
            while self.full_short :
                
                sleep(10)
                self.analyze_market()
            self.log('Bot found its entry point')
            self.telegram_bot_sendtext('Bot found its entry point')
            self.log('Bot is ready...')
            while self.continuer:
                
                sleep(2.0)
                while self.paused:
                    
                    sleep(10)
                self.analyze_market()
                
                self.check_to_do()
                
                self.place_order()
                self.conclude()
                
            self.log('Opérations terminées, bot en veille...')
        else :
            self.log('Bot found its entry point')
            self.telegram_bot_sendtext('Bot found its entry point')
            self.log('Bot is ready...')
            while self.continuer:
                
                sleep(2.0)
                while self.paused:
                    sleep(10)
                self.analyze_market()
                
                self.check_to_do()
                self.place_order()
                self.conclude()
            self.log('Operations terminees, bot en veille...')
            
class NotifBot(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.continuer=True
                    
    def run(self):
        while self.continuer == True:
            Bot.telegram_answer()             
            sleep(0.5)
            
class LogBot(Thread):
    def __init__(self, delay, bot_token, bot_chatID):
        Thread.__init__(self)
        self.delay = delay
        self.bot_token = bot_token2
        self.bot_chatID = bot_chatID
        self.continuer=True
    
    def send_msg(self, msg):
        self.msg=msg
        send_text = 'https://api.telegram.org/bot' + self.bot_token + '/sendMessage?chat_id=' + self.bot_chatID + '&parse_mode=Markdown&text=' + self.msg
        response = requests.get(send_text)
        return response.json()
    
    def send_log(self):
        self.msg=read_log()
        send_text = 'https://api.telegram.org/bot' + self.bot_token + '/sendMessage?chat_id=' + self.bot_chatID + '&parse_mode=Markdown&text=' + self.msg
        response = requests.get(send_text)
        return response.json()
 
    def run(self):
        while self.continuer:
            self.send_log()
            sleep(self.delay*60)


#Interpreteur :

bots = []
indicators = {}
notifbot = NotifBot()
notifbot.start()

while True:

    comm = input('@ : ')
    
    if comm == 'help':
        print("""Aide : liste des commandes : 
- start : Start a new bot
- pause [id/all]
- resume [id/all]
- kill [id/all]
- list
- log
- dellog
- startsendlog [delay_in_min] : send log via telegram ; !! must have created a bot first !!
- stopsendlog : stop sending log via telegram
-startbypass : start bot with bypass mode
- startnotifbot
- stopnotifbot
""")

    elif comm == 'start':
        owner = input('Whose bot is this one ?')
        client = Client(input('Quelle est votre cle publique? : '),input('Quelle est votre cle privee? : '), input('Quelle est votre mot de passe ? : '))
        bot_chatID1 = input('chatID between user and @Trading_Notif_Bot ?')
        base = input('Base asset name (code, in MAJ, no space) ?')
        quote = input('Quote asset name (code, in MAJ, no space) ?')
        paire = '{}-{}'.format(quote,base)
        your_base = input('Amount of base you use ?')
        your_quote = input('Amount of quote you use ?')
        margin_base = input('Amount of base borrowed ?')
        margin_quote = input('Amount of quote borrowed ?')
        if paire not in indicators:
            indicators[paire] = Indicators(paire='{}-{}'.format(quote, base))
        n=Bot(owner, client, bot_chatID1, base, quote, your_base, your_quote, margin_base, margin_quote, indicators=indicators[paire])
        n.start()
        bots.append(n)

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
            for b in bots:
                b.continuer = False
                b.telegram_bot_sendtext('Your bot, trading {}, has been killed'.format(b.paire))
                b.log('bot {} killed'.format(id(b)))
                del b
            bots=[]
        elif ' ' not in comm:
            print('G pa capte')
        else:
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
                          
    elif comm.startswith('startsendlog'):
        bot_token = bot_token2
        bot_chatID = input('bot chat_id ?')
        log_bot = LogBot(int(comm.split(' ')[1]), bot_token, bot_chatID)
        log_bot.start()
        
    elif comm == 'stopsendlog':
        if 'log_bot' not in globals():
            print('Error : log bot never started')
        else:
            log_bot.continuer = False
            del log_bot
            
    elif comm == 'startbypass':
        client = Client(input('Quelle est votre cle publique? : '),input('Quelle est votre cle privee? : '), input('Quelle est votre mot de passe ? : '))
        bot_chatID = input('chatID between user and @Trading_Notif_Bot ?')
        base = input('Base asset name (code, in MAJ, no space) ?')
        quote = input('Quote asset name (code, in MAJ, no space) ?')
        your_base = input('Amount of base you use ?')
        your_quote = input('Amount of quote you use ?')
        margin_base = input('Amount of base borrowed ?')
        margin_quote = input('Amount of quote borrowed ?')
        if paire not in indicators:
            indicators['{}-{}'.format(quote, base)] = Indicators(paire='{}-{}'.format(quote, base))
        n=Bot(client, bot_chatID, base, quote, your_base, your_quote, margin_base, margin_quote, bypass = True)
        n.start()
        bots.append(n)
        
    elif comm.startswith('startnotifbot'):
        if 'notifbot' not in globals():
            notifbot = NotifBot()
            notifbot.start()
            print('notifbot started')
        else : 
            notifbot.continuer = False
            del notifbot
            notifbot = NotifBot()
            notifbot.start()
            print('notifbot started')
            
    elif comm == 'stopnotifbot':
        if 'notifbot' not in globals():
            print('Error : notif bot never started')
        else:
            notifbot.continuer = False
            del notifbot
            print('notifbot stopped')
   
        
    else:
        print('Commande inconnue, veuillez taper "help" pour voir la liste des commandes')

print('Programme termine')
        
        
        
               
        
        
        
        
        
        
        
        
        
