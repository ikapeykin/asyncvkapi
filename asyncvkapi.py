import aiohttp
import asyncio
import time
import json


CALL_INTERVAL = 0.05
MAX_CALLS_IN_EXECUTE = 25


class MessageReceiver:
    def __init__(self, api, get_dialogs_interval=-1):
        self.api = api
        self.get_dialogs_interval = get_dialogs_interval




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

    def __init__(self, group_id, token='', token_file=''):
        self.next_call = 0
        self.longpoll = {}
        self.delayed_list = []
        self.max_delayed = 25
        self.event_loop = asyncio.get_event_loop()

        self.group_id = group_id
        self.token = token
        self.token_file = token_file

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
                        # await handler.sync()
                        return response

                    async def delayed(self, *, _once=False, **dp):
                        if len(handler.delayed_list) >= handler.max_delayed:
                            await handler.sync(True)
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

    async def sync(self, once=False):
        while True:
            dl = self.delayed_list[:25]
            self.delayed_list = self.delayed_list[25:]

            if not dl:
                return

            if len(dl) == 1:
                dc = dl[0]
                response = await self.apiCall(dc.method, dc.params, dc.retry)
                dc.called(response)
                if once:
                    return
                continue

            query = ['return[']
            for num, i in enumerate(dl):
                query.append(self.encodeApiCall(i) + ',')
            query.append('];')
            query = ''.join(query)
            response = await self.execute(query)

            if once:
                return

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
        return json_string


api = AsyncVkApi(group_id=176630236,
                 token='ccc50800ff82bd80c268b329b3fdd27cc2cdc52bd7a66a3b59c8cc6ba92e8c2e707f0bc0a04ed5aa889a0',)
loop = asyncio.get_event_loop()

counter = 0


def cb(resp, req):
    print(resp, req)


async def test(user_id):
    global counter
    for i in range(0, 25):
        await api.messages.send.delayed(peer_id=user_id, message=counter, random_id=0).cb(cb)
        counter += 1


t_s = time.time()

tasks = []
for i in range(0, 20):
    tasks.append(loop.create_task(test(279494346)))
    tasks.append(loop.create_task(test(279494346)))

    tasks.append(api.sync())
loop.run_until_complete(asyncio.wait(tasks))

print(time.time() - t_s)



