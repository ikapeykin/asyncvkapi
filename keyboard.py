import json


class colors:
    RED = 'negative'
    BLUE = 'primary'
    WHITE = 'secondary'
    GREEN = 'positive'


class Keyboard:
    def __init__(self, one_time=False):
        self.keyboard = {'one_time': one_time, 'buttons': []}  # Simple keyboard, which can close other keyboards
        self.buttons = []
        self.new_line_buttons = ('vkpay', 'location', 'open_app')

    def add_button(self, type, text=None, payload=None, color=None, app_id=None, owner_id=None, hash=None, label=None):
        button = {}

        if type == 'location':
            if not payload:
                raise Exception('Button location didn\'t found payload')

            button['action'] = {}
            button['action']['type'] = type
            button['action']['payload'] = payload

        elif type == 'vkpay':
            if not hash:
                raise Exception('Button vkpay didn\'t found hash')

            button['action'] = {}
            button['action']['type'] = type
            button['action']['hash'] = hash

        elif type == 'open_app':
            if not app_id or not owner_id or not label:
                raise Exception('Button open_app didn\'t found some value')

            button['action'] = {}
            button['action']['type'] = type
            button['action']['app_id'] = app_id
            button['action']['owner_id'] = owner_id
            if hash:
                button['action']['hash'] = hash
            button['action']['label'] = label

        elif type == 'text':
            if not label or not color:
                raise Exception('Button text didn\'t found some value')

            button['action'] = {}
            button['action']['type'] = type
            button['action']['label'] = str(label)
            if payload:
                button['action']['payload'] = str(payload)

            button['color'] = color

        else:
            raise Exception('Incorrect type')

        button_type = button['action']['type']

        if button_type in self.new_line_buttons:
            self.add_new_line()
            self.buttons.append(button)
            self.add_new_line()
        else:
            self.buttons.append(button)

    def add_new_line(self):
        if self.buttons:
            self.keyboard['buttons'].append(self.buttons)

        self.buttons = []

    def get_keyboard_json(self):
        self.add_new_line()
        return json.dumps(self.keyboard)