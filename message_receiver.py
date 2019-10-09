import queue
import threading
import time

from multiprocessing import Process, Manager


CONF_START = 2000000000


class MessageReceiver:
    def __init__(self, api, get_dialogs_interval=-1):
        self.api = api
        self.get_dialogs_interval = get_dialogs_interval
        self.longpoll_queue = queue.Queue()
        self.longpoll_thread = threading.Thread(target=self.monitor, daemon=True)
        self.longpoll_thread.start()
        self.longpoll_callback = None
        self.whitelist = []
        self.whitelist_includeread = True
        self.last_message_id = 0
        self.last_get_dialogs = 0
        self.longpolled_messages = set()
        self.used_get_dialogs = False
        self.terminate_monitor = False

    def monitor(self):
        while True:
            try:
                for i in self._getLongpoll():
                    self.longpoll_queue.put(i)
            except Exception:
                time.sleep(0.5)

    def getMessages(self, get_dialogs=False):
        ctime = time.time()
        if not self.last_get_dialogs:
            self.last_get_dialogs = ctime - self.get_dialogs_interval + 1
        if (self.get_dialogs_interval >=0 and ctime - self.last_get_dialogs > self.get_dialogs_interval) or get_dialogs:
            self.used_get_dialogs = True
            self.last_get_dialogs = ctime
            res = []
            if self.whitelist:
                messages = self.api.messages.getDialogs(unread=(0 if self.whitelist_includeread else 1), count=20)
                self.whitelist_includeread = False
            else:
                messages = self.api.messages.getDialogs(unread=1, count=200)
            try:
                messages = messages['items'][::-1]
            except TypeError:
                return []
            for msg in sorted(messages, key=lambda m: m['message']['id']):
                cur = msg['message']
                if cur['out'] or cur['id'] in self.longpolled_messages:
                    continue
                if self.last_message_id and cur['id'] > self.last_message_id:
                    continue  # wtf?
                cur['_method'] = 'getDialogs'
                res.append(cur)
            self.longpolled_messages.clear()
        else:
            self.used_get_dialogs = False
            res = []
            while not self.longpoll_queue.empty():
                res.append(self.longpoll_queue.get())
            res.sort(key=lambda x: x['id'])
            self.longpolled_messages.update(i['id'] for i in res)
            if res:
                self.last_message_id = max(self.last_message_id, res[-1]['id'])
        return res

    async def _getLongpoll(self):
        arr = await self.api.getLongpoll()
        if self.terminate_monitor:
            return []
        need_extra = []
        result = []
        for record in arr:
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

                result.append(msg)

            elif record['type'] == 'vkpay_transaction':
                pass
                # {'type': 'vkpay_transaction', 'object': {'amount': 1000, 'from_id': 334626257, 'description': 'Номер заказа: 15', 'date': 1563328181}, 'group_id': 56400647}

        return result
