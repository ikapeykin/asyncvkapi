import aiohttp
import asyncio
import time
import json


CALL_INTERVAL = 0.05
MAX_CALLS_IN_EXECUTE = 25


class VkMethod:
    def __init__(self, method):
        self.method = method


class DelayedCall:
    def __init__(self, method, params):
        self.method = method
        self.params = params
        self.retry = False
        self.callback_func = None

    async def callback(self, func):
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

        self.group_id = group_id
        self.token = token
        self.token_file = token_file

        self.event_loop = asyncio.get_event_loop()
        self.event_loop.create_task(self.sync())

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

                        res = self.delayed(**dp).callback(cb)
                        return response

                    def delayed(self, *, _once=False, **dp):
                        dc = DelayedCall(self.method, dp)
                        if not _once or dc not in handler.delayed_list:
                            handler.delayed_list.append(dc)
                        return dc

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

            if 'response' in response:
                for dc, r in zip(dl, response['response']):
                    dc.called(r)

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

        return json_string['response']

    async def initLongpoll(self):
        r = await self.groups.getLongPollServer(group_id=self.group_id)

        if not r:
            await self.initLongpoll()

        self.longpoll = {'server': r['server'], 'key': r['key'], 'ts': self.longpoll.get('ts') or r['ts']}

    async def getLongpoll(self):
        longpoll_queue = []

        if not self.longpoll.get('server'):
            await self.initLongpoll()

        url = '{}?act=a_check&key={}&ts={}&wait=25&'.format(
            self.longpoll['server'], self.longpoll['key'], self.longpoll['ts']
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as resp:
                    json_string = await resp.json()

            data_array = json_string

            if 'ts' in data_array:
                self.longpoll['ts'] = data_array['ts']

            if 'updates' in data_array:
                for record in data_array['updates']:
                    if record['type'] == 'message_new':  # new message
                        msg = {}
                        feed = record.get('object')

                        if not msg.get('chat_id'):
                            msg['chat_id'] = feed.get('from_id')

                        msg['body'] = feed.get('text')
                        msg['chat_id'] = feed.get('peer_id')
                        msg['ref'] = feed.get('ref')
                        msg['ref_source'] = feed.get('ref_source')
                        msg['payload'] = feed.get('payload')
                        msg['user_id'] = feed.get('from_id')
                        msg['id'] = feed.get('id')
                        msg['attachments'] = feed.get('attachments')

                        longpoll_queue.append(msg)


            elif data_array['failed'] != 1:
                await self.initLongpoll()

        except Exception as e:
            pass

        return longpoll_queue


