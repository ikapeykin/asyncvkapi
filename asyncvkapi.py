import aiohttp
import asyncio
import time
import json
import ssl


CALL_INTERVAL = 0.05
MAX_CALLS_IN_EXECUTE = 25


class DelayedCall:
    def __init__(self, method, params):
        self.method = method
        self.params = params
        self.retry = False
        self.callback_func = None

    def callback(self, func):
        self.callback_func = func
        return self

    def called(self, response):
        if self.callback_func:
            self.callback_func(self.params, response)

    def __eq__(self, a):
        return self.method == a.method and self.params == a.params and self.callback_func is None and a.callback_func is None


class AsyncVkApi:
    api_version = '5.95'

    def __init__(self, group_id, event_loop, token='', token_file=''):
        self.next_call = 0
        self.longpoll = {}
        self.delayed_list = []
        self.max_delayed = 25
        self.event_loop = asyncio.get_event_loop()

        self.group_id = group_id
        self.token = token
        self.token_file = token_file

        self.event_loop = asyncio.get_event_loop()
        event_loop.create_task(self.sync())

    def __getattr__(self, item):
        handler = self

        class _GroupWrapper:
            def __init__(self, group):
                self.group = group

            def __getattr__(self, subitem):
                class _MethodWrapper:
                    def __init__(self, method):
                        self.method = method

                    async def __call__(self, **dp):
                        response = None

                        def cb(req, resp):
                            nonlocal response
                            response = resp

                        res = await self.delayed(**dp)
                        res.callback(cb)
                        await handler.sync()
                        return response

                    async def delayed(self, *, _once=False, **dp):
                        dc = DelayedCall(self.method, dp)
                        if not _once or dc not in handler.delayed_list:
                            handler.delayed_list.append(dc)
                        return dc

                    async def walk(self, callback, **dp):
                        async def cb(req, resp):
                            callback(req, resp)
                            if resp is None:
                                return
                            if 'next_from' in resp:
                                if resp['next_from']:
                                    req['start_from'] = resp['next_from']
                                    res = await self.delayed(**req)
                                    res.callback(cb)
                            elif 'count' in resp and 'count' in req and req['count'] + req.get('offset', 0) < resp['count']:
                                req['offset'] = req.get('offset', 0) + req['count']
                                res = await self.delayed(**req)
                                res.callback(cb)

                        res = await self.delayed(**dp)
                        res.callback(cb)
                        return handler

                return _MethodWrapper(self.group + '.' + subitem)

        return _GroupWrapper(item)

    async def execute(self, code):
        return await self.apiCall('execute', {"code": code}, full_response=True)

    @staticmethod
    def encodeApiCall(s):
        return "API." + s.method + '(' + json.dumps(s.params, ensure_ascii=False) + ')'

    async def sync(self):
        dl = self.delayed_list[:25]
        self.delayed_list = self.delayed_list[25:]

        if len(dl) == 1:
            dc = dl[0]
            response = await self.apiCall(dc.method, dc.params, dc.retry)
            dc.called(response)

        elif len(dl):
            query = ['return[']
            for num, i in enumerate(dl):
                query.append(self.encodeApiCall(i) + ',')
            query.append('];')
            query = ''.join(query)
            response = await self.execute(query)

        await asyncio.sleep(CALL_INTERVAL)
        self.event_loop.create_task(self.sync())

    async def apiCall(self, method, params, retry=False, full_response=False):
        current_time = time.time()
        if current_time < self.next_call:
            self.next_call += CALL_INTERVAL
            await asyncio.sleep(self.next_call - current_time)
        else:
            self.next_call = CALL_INTERVAL + time.time()

        params['v'] = self.api_version

        url = 'https://api.vk.com/method/' + method + '?access_token=' + self.token
        post_params = params

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=post_params) as resp:
                json_string = await resp.json()
                print(json_string)

        return json_string['response']

    async def initLongpoll(self):
        r = await self.groups.getLongPollServer(group_id=self.group_id)

        if not r:
            await self.initLongpoll()

        self.longpoll = {'server': r['server'], 'key': r['key'], 'ts': self.longpoll.get('ts') or r['ts']}

    async def getLongpoll(self):
        if not self.longpoll.get('server'):
            await self.initLongpoll()

        url = '{}?act=a_check&key={}&ts={}&wait=25&'.format(
            self.longpoll['server'], self.longpoll['key'], self.longpoll['ts']
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30, ssl=False) as resp:
                    json_string = await resp.json()

            data_array = json_string

            if 'ts' in data_array:
                self.longpoll['ts'] = data_array['ts']

            if 'updates' in data_array:
                print(data_array['updates'])

            elif data_array['failed'] != 1:
                await self.initLongpoll()

        except Exception as e:
            pass

        await asyncio.sleep(CALL_INTERVAL*2)
        self.event_loop.create_task(self.getLongpoll())




loop = asyncio.get_event_loop()
api = AsyncVkApi(group_id=176630236,
                 token='ccc50800ff82bd80c268b329b3fdd27cc2cdc52bd7a66a3b59c8cc6ba92e8c2e707f0bc0a04ed5aa889a0',
                 event_loop=loop)

loop.create_task(api.getLongpoll())

async def test():
    print('Something just')
    await api.messages.send.delayed(peer_id=334626257, message='Its work))', random_id=0)

loop.create_task(test())
loop.run_forever()
