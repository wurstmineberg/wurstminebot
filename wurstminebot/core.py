import sys

sys.path.append('/opt/py')

import TwitterAPI
from datetime import datetime
import json
import minecraft
from wurstminebot import nicksub
import os.path
import re
import requests
import threading
import time
import traceback
import xml.sax.saxutils

class ErrorMessage:
    log = "I can't find that in my chatlog"

    @staticmethod
    def argc(expected, given, atleast=False):
        return ('not enough' if given < expected else 'too many') + ' arguments, expected ' + ('at least ' if atleast else '') + str(expected)

    @staticmethod
    def unknown(command=None):
        if command is None or command == '':
            return 'Unknown command. Execute “help commands” for a list of commands, or “help aliases” for a list of aliases.'
        else:
            return '“' + str(command) + '” is not a command. Execute “help commands” for a list of commands, or “help aliases” for a list of aliases.'

    @staticmethod
    def permission(level=0):
        if level == 1:
            return 'you must be in people.json to do this'
        elif level == 2:
            return 'this command requires a server invite'
        elif level == 3:
            return 'you must be on the whitelist to do this'
        elif level == 4:
            return 'you must be a bot op to do this'
        else:
            return "you don't have permission to do this"

class TwitterError(Exception):
    def __init__(self, code, message=None, status_code=0):
        self.code = code
        self.message = message
        self.status_code = status_code

    def __str__(self):
        return str(self.code) if self.message is None else str(self.message)

def cleanup():
    if state.get('input_loop') is not None:
        state['input_loop'].stop()
    state['input_loop'] = None
    if state.get('time_loop') is not None:
        state['time_loop'].stop()
    state['time_loop'] = None
    if state.get('bot') is not None:
        state['bot'].stop()
    state['bot'] = None

def config(key=None, default_value=None):
    default_config = {
        'aliases': {
            'dg': {
                'command_name': 'DeathGames',
                'type': 'command'
            },
            'mwiki': {
                'command_name': 'MinecraftWiki',
                'type': 'command'
            },
            'opt': {
                'command_name': 'Option',
                'type': 'command'
            },
            'ping': {
                'text': 'pong',
                'type': 'reply'
            }
        },
        'advanced_comment_lines': {
            'death': [],
            'server_join': []
        },
        'comment_lines': {
            'death': ['Well done.'],
            'server_join': []
        },
        'daily_restart': True,
        'death_games': {
            'logfile': '/opt/wurstmineberg/config/deathgames.json',
            'enabled': False
        },
        'debug': False,
        'irc': {
            'channels': [],
            'dev_channel': None,
            'live_channel': None,
            'live_topic': None,
            'main_channel': '#wurstmineberg',
            'nick': 'wurstminebot',
            'op_nicks': [],
            'password': '',
            'player_list': 'announce',
            'port': 6667,
            'quit_messages': ['brb'],
            'ssl': False,
            'topic': None
        },
        'ops': [],
        'paths': {
            'assets': '/var/www/wurstmineberg.de/assets/serverstatus',
            'deathgames': '/opt/wurstmineberg/log/deathgames.json',
            'keepalive': '/var/local/wurstmineberg/wurstminebot_keepalive',
            'logs': '/opt/wurstmineberg/log',
            'minecraft_server': '/opt/wurstmineberg/server',
            'people': '/opt/wurstmineberg/config/people.json',
            'scripts': '/opt/wurstmineberg/bin'
        },
        'twitter': {
            'screen_name': 'wurstmineberg'
        }
    }
    try:
        with open(state['config_path']) as config_file:
            j = json.load(config_file)
    except:
        j = default_config
    if key is None:
        return j
    return j.get(key, default_config.get(key)) if default_value is None else j.get(key, default_value)

def death_games_log(attacker, target, success=True):
    with open(config('paths').get('deathgames', '/opt/wurstmineberg/log/deathgames.json')) as logfile:
        log = json.load(logfile)
    log['log'].append({
        'attacker': attacker.id,
        'date': datetime.utcnow().strftime('%Y-%m-%d'),
        'success': success,
        'target': target.id
    })
    with open(config('paths').get('deathgames', '/opt/wurstmineberg/log/deathgames.json'), 'w') as logfile:
        json.dump(log, logfile, sort_keys=True, indent=4, separators=(',', ': '))
    minecraft.tellraw([
        {
            'text': '[Death Games]',
            'clickEvent': {
                'action': 'open_url',
                'value': 'http://wiki.wurstmineberg.de/Death_Games'
            },
            'color': 'gold'
        },
        {
            'text': ' ',
            'color': 'gold'
        },
        {
            'text': attacker.minecraft,
            'clickEvent': {
                'action': 'suggest_command',
                'value': attacker.minecraft + ': '
            },
            'color': 'gold'
        },
        {
            'text': "'s attempt on ",
            'color': 'gold'
        },
        {
            'text': target.minecraft,
            'clickEvent': {
                'action': 'suggest_command',
                'value': target.minecraft + ': '
            },
            'color': 'gold'
        },
        {
            'text': (' succeeded.' if success else ' failed.'),
            'color': 'gold'
        }
    ])
    irc_config = config('irc')
    if 'main_channel' in irc_config:
        state['bot'].say(irc_config['main_channel'], '[Death Games] ' + attacker.irc_nick() + "'s attempt on " + target.irc_nick() + (' succeeded.' if success else ' failed.'))

def debug_print(msg):
    if config('debug', False):
        print('DEBUG] ' + msg)

def minecraft_wiki_lookup(article, reply=None):
    if reply is None:
        def reply(*args, **kwargs):
            pass
    
    match = re.match('http://(?:minecraft\\.gamepedia\\.com|minecraftwiki\\.net(?:/wiki)?)/(.*)', article)
    if match:
        article = match.group(1)
    request = requests.get('http://minecraft.gamepedia.com/' + article, params={'action': 'raw'})
    if request.status_code == 200:
        if request.text.lower().startswith('#redirect'):
            match = re.match('#[Rr][Ee][Dd][Ii][Rr][Ee][Cc][Tt] \\[\\[(.+)(\\|.*)?\\]\\]', request.text)
            if match:
                redirect_target = 'http://minecraft.gamepedia.com/' + re.sub(' ', '_', match.group(1))
                reply('Redirect ' + redirect_target)
                return 'Redirect ' + redirect_target
            else:
                reply('Broken redirect')
                return 'Broken redirect'
        else:
            reply('Article http://minecraft.gamepedia.com/' + article)
            return 'Article http://minecraft.gamepedia.com/' + article
    else:
        reply('Error ' + str(request.status_code))
        return 'Error ' + str(request.status_code)

def parse_version_string():
    try:
        with open('/opt/hub/wurstmineberg/wurstminebot/README.md') as readme:
            for line in readme.read().splitlines():
                if line.startswith('This is `wurstminebot` version'):
                    return line.split(' ')[4]
    except:
        pass

def parse_timedelta(time_string):
    ret = 0
    time_string = time_string[:]
    while len(time_string) > 0:
        match = re.match('([0-9]+)([dhms])', time_string)
        if not match:
            if re.match('[0-9]+$', time_string):
                return ret + int(time_string)
            else:
                raise ValueError(str(time_string) + ' is not a valid time interval')
        number, unit = match.group(1, 2)
        ret += int(number) * {
            'd': 86400,
            'h': 3600,
            'm': 60,
            's': 1
        }[unit]
        time_string = time_string[len(number) + 1:]
    return ret

def paste_mojira(project, issue_id, link=False, tellraw=False):
    request = requests.get('http://mojang.atlassian.net/browse/' + project + '-' + str(issue_id))
    if request.status_code == 200:
        match = re.match('<title>\\[([A-Z]+)-([0-9]+)\\] (.+) - Mojira</title>', request.text.splitlines()[18])
        if not match:
            if tellraw:
                return {
                    'text': 'could not get title',
                    'color': 'red'
                }
            else:
                return 'could not get title'
        title = match.group(3)
        if tellraw:
            return {
                'text': '[' + project + '-' + issue_id + '] ' + title,
                'color': 'gold',
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'http://mojang.atlassian.net/browse/' + project + '-' + issue_id
                }
            }
        else:
            return '[' + project + '-' + issue_id + '] ' + title + (' [http://mojang.atlassian.net/browse/' + project + '-' + issue_id + ']' if link else '')
    elif tellraw:
        return {
            'text': 'Error ' + str(request.status_code),
            'color': 'red'
        }
    else:
        return 'Error ' + str(request.status_code)

def paste_tweet(status, link=False, tellraw=False):
    r = twitter.request('statuses/show', {'id': status})
    if isinstance(r, TwitterAPI.TwitterResponse):
        j = r.response.json()
    else:
        j = r.json()
    if r.status_code != 200:
        raise TwitterError(j.get('errors', {}).get('code', 0), message=j.get('errors', {}).get('message'), status_code=r.status_code)
    if 'retweeted_status' in j:
        retweeted_request = twitter.request('statuses/show', {'id': j['retweeted_status']['id']})
        if isinstance(retweeted_request, TwitterAPI.TwitterResponse):
            rj = retweeted_request.response.json()
        else:
            rj = retweeted_request.json()
        if retweeted_request.status_code != 200:
            raise TwitterError(rj.get('errors', {}).get('code', 0), message=rj.get('errors', {}).get('message'), status_code=retweeted_request.status_code)
        tweet_author = '<@' + j['user']['screen_name'] + ' RT @' + rj['user']['screen_name'] + '> '
        tweet_author_tellraw = [
            {
                'text': '@' + j['user']['screen_name'],
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'https://twitter.com/' + j['user']['screen_name']
                },
                'color': 'gold'
            },
            {
                'text': ' RT ',
                'color': 'gold'
            },
            {
                'text': '@' + rj['user']['screen_name'],
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'https://twitter.com/' + rj['user']['screen_name']
                },
                'color': 'gold'
            }
        ]
        text = xml.sax.saxutils.unescape(rj['text'])
    else:
        tweet_author = '<@' + j['user']['screen_name'] + '> '
        tweet_author_tellraw = [
            {
                'text': '@' + j['user']['screen_name'],
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'https://twitter.com/' + j['user']['screen_name']
                },
                'color': 'gold'
            }
        ]
        text = xml.sax.saxutils.unescape(j['text'])
    tweet_url = 'https://twitter.com/' + j['user']['screen_name'] + '/status/' + j['id_str']
    if tellraw:
        return {
            'text': '<',
            'color': 'gold',
            'extra': tweet_author_tellraw + [
                {
                    'text': '> ' + text,
                    'color': 'gold'
                }
            ] + ([
                {
                    'text': ' [',
                    'color': 'gold'
                },
                {
                    'text': tweet_url,
                    'clickEvent': {
                        'action': 'open_url',
                        'value': tweet_url
                    },
                    'color': 'gold'
                },
                {
                    'text': ']',
                    'color': 'gold'
                }
            ] if link else [])
        }
    else:
        return tweet_author + text + ((' [' + tweet_url + ']') if link else '')

def run():
    from wurstminebot import loops
    state['time_loop'] = loops.TimeLoop()
    state['time_loop'].start()
    try:
        from wurstminebot import irc
    except ImportError as e:
        debug_print(str(e))
        sys.exit(1)
    else:
        state['bot'] = irc.bot()
        state['bot'].debugging(config('debug'))
        try:
            state['bot'].run()
        except Exception:
            cleanup()
            debug_print('Exception in bot.run:')
            if config('debug', False):
                traceback.print_exc()
            sys.exit(1)
    cleanup()

def set_config(config_dict):
    with open(state['config_path'], 'w') as config_file:
        json.dump(config_dict, config_file, sort_keys=True, indent=4, separators=(',', ': '))

def set_twitter(person, screen_name):
    person.twitter = screen_name
    members_list_id = config('twitter').get('members_list')
    if members_list_id is not None:
        twitter.request('lists/members/create', {'list_id': members_list_id, 'screen_name': screen_name})
    twitter.request('friendships/create', {'screen_name': screen_name})

def status(pidfile):
    if pidfile.is_locked():
        return os.path.exists(os.path.join('/proc/', str(pidfile.read_pid())))
    return False

def tweet(status):
    r = twitter.request('statuses/update', {'status': status})
    if isinstance(r, TwitterAPI.TwitterResponse):
        j = r.response.json()
    else:
        j = r.json()
    if r.status_code == 200:
        return j['id']
    first_error = j.get('errors', [])[0] if len(j.get('errors', [])) else {}
    raise TwitterError(first_error.get('code', 0), message=first_error.get('message'), status_code=r.status_code)

def update_config(path, value):
    config_dict = config()
    full_config_dict = config_dict
    if len(path) > 1:
        for key in path[:-1]:
            if not isinstance(config_dict, dict):
                raise KeyError('Trying to update a non-dict config key')
            if key not in config_dict:
                config_dict[key] = {}
            config_dict = config_dict[key]
    if len(path) > 0:
        config_dict[path[-1]] = value
    else:
        full_config_dict = value
    set_config(full_config_dict)

def update_all(force=False):
    def _try_update_status():
        try:
            minecraft.update_status()
        except (IOError, OSError):
            debug_print('Did not update status due to a FileNotFoundError')
    
    _try_update_status()
    try:
        minecraft.update_whitelist()
    except (IOError, OSError):
        debug_print('Did not update whitelist due to a FileNotFoundError')
    update_topic(force=force)
    threading.Timer(20, _try_update_status).start()

def update_topic(force=False, special_status=None):
    from wurstminebot import irc
    main_channel = config('irc').get('main_channel')
    if main_channel is None:
        return
    players = []
    if special_status is None:
        for mcnick in (minecraft.online_players() if config('irc').get('player_list', 'announce') == 'topic' else []):
            try:
                person = nicksub.Person(mcnick, context='minecraft').irc_nick(respect_highlight_option=False)
            except nicksub.PersonNotFoundError:
                person = mcnick
            players.append(person)
        server_status = ('Currently online: ' + ', '.join(players)) if len(players) else None
    else:
        server_status = special_status
    topic = config('irc').get('topic')
    if topic is None or topic == '':
        new_topic = server_status
    elif server_status is None or server_status == '':
        new_topic = topic
    else:
        new_topic = topic + ' | ' + server_status
    irc.set_topic(main_channel, new_topic, force=force)

__version__ = str(parse_version_string())

permission_levels = [
    None,
    'sender must be in people.json',
    'requires invite',
    'whitelisted only',
    'bot-ops only'
]

state = {
    'achievement_tweets': True,
    'bot': None,
    'config_path': '/opt/wurstmineberg/config/wurstminebot.json',
    'death_tweets': True,
    'dst': bool(time.localtime().tm_isdst),
    'input_loop': None,
    'irc_topics': {},
    'last_death': '',
    'log_lock': threading.Lock(),
    'time_loop': None
}

try:
    twitter = TwitterAPI.TwitterAPI(config('twitter')['consumer_key'], config('twitter')['consumer_secret'], config('twitter')['access_token_key'], config('twitter')['access_token_secret'])
except KeyError:
    twitter = None
