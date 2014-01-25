from wurstminebot import commands
from wurstminebot import core
from datetime import datetime
from wurstminebot import deaths
import json
import minecraft
from wurstminebot import nicksub
import os.path
import random
import re
import socket
import threading
import time
import traceback

class InputLoop(threading.Thread):
    def __init__(self):
        super().__init__(name='wurstminebot InputLoop')
        self.stopped = False
    
    @staticmethod
    def process_log_line(log_line):
        try:
            # server log output processing
            core.debug_print('[logpipe] ' + log_line)
            matches = {
                'achievement': minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') has just earned the achievement \\[(.+)\\]$',
                'action': minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: \\* (' + minecraft.regexes.player + ') (.*)',
                'chat_message': minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: <(' + minecraft.regexes.player + ')> (.*)',
                'join_leave': '(' + minecraft.regexes.timestamp + ') \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') (left|joined) the game'
            }
            for match_type, match_string in matches.items():
                match = re.match(match_string, log_line)
                if not match:
                    continue
                if match_type == 'achievement':
                    player, achievement = match.group(1, 2)
                    person = nicksub.person_or_dummy(player, context='minecraft')
                    if core.state['achievement_tweets']:
                        twitter_nick = person.nick('twitter', twitter_at_prefix=True)
                        status = '[Achievement Get] ' + twitter_nick + ' got ' + achievement
                        try:
                            twid = core.tweet(status)
                        except core.TwitterError as e:
                            twid = 'error ' + str(e.status_code) + ': ' + str(e)
                        else:
                            twid = 'https://twitter.com/wurstmineberg/status/' + str(twid)
                    else:
                        twid = 'achievement tweets are disabled'
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config:
                        core.state['bot'].say(irc_config['main_channel'], 'Achievement Get: ' + person.irc_nick() + ' got ' + achievement + ' [' + twid + ']')
                elif match_type == 'action':
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config:
                        player, message = match.group(1, 2)
                        try:
                            sender_person = nicksub.Person(player, context='minecraft')
                        except nicksub.PersonNotFoundError:
                            sender_person = None
                        sender = player if sender_person is None else sender_person.irc_nick()
                        subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                        core.state['bot'].log(irc_config['main_channel'], 'ACTION', sender, [irc_config['main_channel']], subbed_message)
                        core.state['bot'].say(irc_config['main_channel'], '* ' + sender + ' ' + subbed_message)
                elif match_type == 'chat_message':
                    player, message = match.group(1, 2)
                    try:
                        sender_person = nicksub.Person(player, context='minecraft')
                    except nicksub.PersonNotFoundError:
                        sender_person = None
                    if message.startswith('!') and not re.match('!+$', message):
                        # command
                        cmd = message[1:].split(' ')
                        try:
                            commands.run(cmd, sender=(player if sender_person is None else sender_person), context='minecraft')
                        except SystemExit:
                            core.debug_print('Exit in ' + str(cmd[0]) + ' command from ' + str(player) + ' to in-game chat')
                            core.cleanup()
                            raise
                        except core.TwitterError as e:
                            minecraft.tellraw({
                                'text': 'Error ' + str(e.status_code) + ': ' + str(e),
                                'color': 'red'
                            }, str(player))
                            core.debug_print('TwitterError ' + str(e.status_code) + ' in ' + str(cmd[0]) + ' command from ' + str(player) + ' to in-game chat:')
                            core.debug_print(json.dumps(e.errors, sort_keys=True, indent=4, separators=(',', ': ')))
                        except Exception as e:
                            minecraft.tellraw({
                                'text': 'Error: ' + str(e),
                                'color': 'red'
                            }, str(player))
                            core.debug_print('Exception in ' + str(cmd[0]) + ' command from ' + str(player) + ' to in-game chat:')
                            if core.config('debug', False):
                                traceback.print_exc()
                    else:
                        # chat message
                        irc_config = core.config('irc')
                        if 'main_channel' in irc_config:
                            sender = player if sender_person is None else sender_person.irc_nick()
                            subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                            core.state['bot'].log(irc_config['main_channel'], 'PRIVMSG', sender, [irc_config['main_channel']], subbed_message)
                            core.state['bot'].say(irc_config['main_channel'], '<' + sender + '> ' + subbed_message)
                elif match_type == 'join_leave':
                    timestamp, player = match.group(1, 2)
                    try:
                        person = nicksub.Person(player, context='minecraft')
                    except PersonNotFoundError:
                        person = None
                    joined = bool(match.group(3) == 'joined')
                    with open(os.path.join(core.config('paths')['logs'], 'logins.log')) as loginslog:
                        for line in loginslog:
                            if player in line:
                                new_player = False
                                break
                        else:
                            new_player = True
                    with open(os.path.join(core.config('paths')['logs'], 'logins.log'), 'a') as loginslog:
                        print(timestamp + ' ' + player + ' ' + ('joined' if joined else 'left') + ' the game', file=loginslog)
                    if joined:
                        if new_player:
                            welcome_message = (0, 2) # The “welcome to the server” message
                        else:
                            welcome_messages = dict(((1, index), 1.0) for index in range(len(core.config('comment_lines').get('server_join', []))))
                            if person is None:
                                welcome_message = (0, -1) # The “how did you do that?” fallback welcome message
                            else:
                                if person.description is None:
                                    welcome_messages[0, 1] = 1.0 # The “you still don't have a description” welcome message
                                for index, adv_welcome_msg in enumerate(core.config('advanced_comment_lines').get('server_join', [])):
                                    if 'text' not in adv_welcome_msg:
                                        continue
                                    welcome_messages[2, index] = adv_welcome_msg.get('weight', 1.0) * adv_welcome_msg.get('player_weights', {}).get(player, adv_welcome_msg.get('player_weights', {}).get('@default', 1.0))
                                random_index = random.uniform(0.0, sum(welcome_messages.values()))
                                index = 0.0
                                for welcome_message, weight in welcome_messages.items():
                                    if random_index - index < weight:
                                        break
                                    else:
                                        index += weight
                                else:
                                    welcome_message = (0, 0) # The “um… sup?” welcome message
                        if welcome_message == (0, 0):
                            minecraft.tellraw({
                                'text': 'Hello ' + player + '. Um... sup?',
                                'color': 'gray'
                            }, player)
                        if welcome_message == (0, 1):
                            minecraft.tellraw([
                                {
                                    'text': 'Hello ' + player + ". You still don't have a description for ",
                                    'color': 'gray'
                                },
                                {
                                    'text': 'the people page',
                                    'hoverEvent': {
                                        'action': 'show_text',
                                        'value': 'http://wurstmineberg.de/people'
                                    },
                                    'clickEvent': {
                                        'action': 'open_url',
                                        'value': 'http://wurstmineberg.de/people'
                                    },
                                    'color': 'gray'
                                },
                                {
                                    'text': '. ',
                                    'color': 'gray'
                                },
                                {
                                    'text': 'Write one today',
                                    'clickEvent': {
                                        'action': 'suggest_command',
                                        'value': '!people ' + person.id + ' description '
                                    },
                                    'color': 'gray'
                                },
                                {
                                    'text': '!',
                                    'color': 'gray'
                                }
                            ], player)
                        elif welcome_message == (0, 2):
                            minecraft.tellraw({
                                'text': 'Hello ' + player + '. Welcome to the server!',
                                'color': 'gray'
                            }, player)
                        elif welcome_message[0] == 1:
                            minecraft.tellraw({
                                'text': 'Hello ' + player + '. ' + core.config('comment_lines')['server_join'][welcome_message[1]],
                                'color': 'gray'
                            }, player)
                        elif welcome_message[0] == 2:
                            message_dict = core.config('advanced_comment_lines')['server_join'][welcome_message[1]]
                            message_list = message_dict['text']
                            if isinstance(message_list, str):
                                message_list = [{'text': message_list, 'color': 'gray'}]
                            elif isinstance(message_list, dict):
                                message_list = [message_list]
                            minecraft.tellraw(([
                                {
                                    'text': 'Hello ' + player + '. ',
                                    'color': 'gray'
                                }
                            ] if message_dict.get('hello_prefix', True) else []) + message_list, player)
                        else:
                            minecraft.tellraw({
                                'text': 'Hello ' + player + '. How did you do that?',
                                'color': 'gray'
                            }, player)
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config and irc_config.get('player_list', 'announce') == 'announce':
                        core.state['bot'].say(irc_config['main_channel'], (player if person is None else person.irc_nick()) + ' ' + ('joined' if joined else 'left') + ' the game')
                    core.update_all()
                break
            else:
                try:
                    death = deaths.Death(log_line)
                except ValueError:
                    return # no death, continue parsing here or ignore this line
                with open(os.path.join(core.config('paths')['logs'], 'deaths.log'), 'a') as deathslog:
                    print(death.timestamp.strftime('%Y-%m-%d %H:%M:%S') + ' ' + death.message(), file=deathslog)
                if core.state['death_tweets']:
                    if death.message() == core.state['last_death']:
                        comment = 'Again.' # This prevents botspam if the same player dies lots of times (more than twice) for the same reason.
                    elif (death.id == 'slain-player-using' and death.groups[1] == 'Sword of Justice') or (death.id == 'shot-player-using' and death.groups[1] == 'Bow of Justice'): # Death Games success
                        comment = 'And loses a diamond http://wiki.wurstmineberg.de/Death_Games'
                        try:
                            target = nicksub.Person(death.groups[0], context='minecraft')
                        except nicksub.PersonNotFoundError:
                            pass # don't automatically log
                        else:
                            death_games_log(death.person, target, success=True)
                    else:
                        death_comments = dict(((1, index), 1.0) for index in range(len(core.config('comment_lines').get('death', []))))
                        for index, adv_death_comment in enumerate(core.config('advanced_comment_lines').get('death', [])):
                            if 'text' not in adv_death_comment:
                                continue
                            try:
                                death_comments[2, index] = adv_death_comment.get('weight', 1.0) * adv_death_comment.get('player_weights', {}).get(death.player.id, adv_death_comment.get('player_weights', {}).get('@default', 1.0)) * adv_death_comment.get('type_weights', {}).get(death.id, adv_death_comment.get('type_weights', {}).get('@default', 1.0))
                            except:
                                continue
                        random_index = random.uniform(0.0, sum(death_comments.values()))
                        index = 0.0
                        for comment_index, weight in death_comments.items():
                            if random_index - index < weight:
                                break
                            else:
                                index += weight
                        else:
                            comment_index = (0, 0)
                        if comment_index == (0, 0):
                            comment = 'Well done.'
                        elif comment_index[0] == 1:
                            comment = core.config('comment_lines')['death'][comment_index[1]]
                        elif comment_index[0] == 2:
                            comment = core.config('advanced_comment_lines')['death'][comment_index[1]]['text']
                        else:
                            comment = "I don't even."
                    core.state['last_death'] = death.message()
                    status = death.tweet(comment=comment)
                    try:
                        twid = core.tweet(status)
                    except core.TwitterError as e:
                        twid = 'error ' + str(e.status_code) + ': ' + str(e)
                        minecraft.tellraw([
                            {
                                'text': 'Your fail has ',
                                'color': 'gold'
                            },
                            {
                                'text': 'not',
                                'color': 'red'
                            },
                            {
                                'text': ' been reported because of ',
                                'color': 'gold'
                            },
                            {
                                'text': 'reasons',
                                'hoverEvent': {
                                    'action': 'show_text',
                                    'value': str(e.status_code) + ': ' + str(e)
                                },
                                'color': 'gold'
                            },
                            {
                                'text': '.',
                                'color': 'gold'
                            }
                        ])
                    else:
                        twid = 'https://twitter.com/wurstmineberg/status/' + str(twid)
                        minecraft.tellraw({
                            'text': 'Your fail has been reported. Congratulations.',
                            'color': 'gold',
                            'clickEvent': {
                                'action': 'open_url',
                                'value': twid
                            }
                        })
                else:
                    twid = 'deathtweets are disabled'
                core.debug_print('[death] ' + death.irc_message(tweet_info=twid))
                irc_config = core.config('irc')
                if 'main_channel' in irc_config:
                    core.state['bot'].say(irc_config['main_channel'], death.irc_message(tweet_info=twid))
        except SystemExit:
            core.debug_print('Exit in log input loop')
            core.input_loop.stop()
            core.time_loop.stop()
            raise
        except:
            core.debug_print('Exception in log input loop:')
            if core.state.get('is_daemon', False) or core.config('debug', False):
                traceback.print_exc()
    
    def run(self):
        for log_line in log_tail():
            if self.stopped or not core.state['bot'].keepGoing:
                break
            InputLoop.process_log_line(log_line)
    
    def start(self):
        self.stopped = False
        super().start()
    
    def stop(self):
        self.stopped = True

class TimeLoop(threading.Thread):
    def __init__(self):
        super().__init__(name='wurstminebot TimeLoop')
        self.stopped = False
    
    def run(self):
        #FROM http://stackoverflow.com/questions/9918972/running-a-line-in-1-hour-intervals-in-python
        # modified to work with leap seconds
        while not self.stopped:
            # sleep for the remaining seconds until the next hour
            time_until_hour = 3601 - time.time() % 3600
            while time_until_hour >= 60:
                time.sleep(60)
                if self.stopped:
                    break
                time_until_hour -= 60
            while time_until_hour >= 1:
                time.sleep(1)
                if self.stopped:
                    break
                time_until_hour -= 1
            if self.stopped:
                break
            tell_time(comment=True, restart=core.config('daily_restart', True))
    
    def start(self):
        self.stopped = False
        super().start()
    
    def stop(self):
        self.stopped = True

def log_tail(timeout=0.5):
    logpath = os.path.join(core.config('paths')['minecraft_server'], 'logs', 'latest.log')
    try:
        with open(logpath) as log:
            lines_read = len(list(log.read().split('\n'))) - 1 # don't yield lines that already existed
    except (IOError, OSError):
        lines_read = 0
    while True:
        time.sleep(timeout)
        try:
            with open(logpath) as log:
                lines = log.read().split('\n')
                if len(lines) <= lines_read: # log has restarted
                    lines_read = 0
                for line in lines[lines_read:-1]:
                    lines_read += 1
                    yield line
        except (IOError, OSError):
            core.debug_print('Log does not exist, retrying in 10 seconds')
            time.sleep(10)

def tell_time(func=None, comment=False, restart=False):
    if func is None:
        def func(msg):
            for line in msg.splitlines():
                try:
                    minecraft.tellraw({
                        'text': line,
                        'color': 'gold'
                    })
                except socket.error:
                    core.debug_print('telltime is disconnected from Minecraft')
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config:
                        core.state['bot'].say(irc_config['main_channel'], 'Warning! Telltime is disconnected from Minecraft.')
                    break
    
        custom_func = False
    else:
        custom_func = True
    def warning(msg):
        if custom_func:
            func(msg)
        else:
            for line in msg.splitlines():
                try:
                    minecraft.tellraw({
                        'text': line,
                        'color': 'red'
                    })
                except socket.error:
                    core.debug_print('telltime is disconnected from Minecraft')
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config:
                        core.state['bot'].say(irc_config['main_channel'], 'Warning! Telltime is disconnected from Minecraft.')
                    break
    
    localnow = datetime.now()
    utcnow = datetime.utcnow()
    dst = bool(time.localtime().tm_isdst)
    if dst != core.state['dst']:
        if dst:
            func('Daylight saving time is now in effect.')
        else:
            func('Daylight saving time is no longer in effect.')
    func('The time is ' + localnow.strftime('%H:%M') + ' (' + utcnow.strftime('%H:%M') + ' UTC)')
    if comment:
        if dst != core.state['dst']:
            pass
        elif localnow.hour == 0:
            func('Dark outside, better play some Minecraft.')
        elif localnow.hour == 1:
            func("You better don't stay up all night again.")
        elif localnow.hour == 2:
            func('Some late night mining always cheers me up.')
            time.sleep(10)
            func('...Or redstoning. Or building. Whatever floats your boat.')
        elif localnow.hour == 3:
            func('Seems like you are having fun.')
            time.sleep(60)
            func("I heard that zombie over there talk trash about you. Thought you'd wanna know...")
        elif localnow.hour == 4:
            func('Getting pretty late, huh?')
        elif localnow.hour == 5:
            warning('It is really getting late. You should go to sleep.')
        elif localnow.hour == 6:
            func('Are you still going, just starting or asking yourself the same thing?')
        elif localnow.hour == 11 and localnow.minute < 5 and restart:
            players = nicksub.sorted_people(minecraft.online_players(), context='minecraft')
            if len(players):
                warning('The server is going to restart in 5 minutes.')
                time.sleep(240)
                warning('The server is going to restart in 60 seconds.')
                time.sleep(50)
            core.update_topic(special_status='The server is restarting…')
            irc_config = core.config('irc')
            if minecraft.restart(reply=func):
                if len(players) and 'main_channel' in irc_config:
                    core.state['bot'].say(irc_config['main_channel'], ', '.join(player.irc_nick(respect_highlight_option=False) for player in irc_players) + ': The server has restarted.')
            else:
                core.debug_print('daily server restart failed')
                if 'main_channel' in irc_config:
                    core.state['bot'].say(irc_config['main_channel'], 'Please help! Something went wrong with the server restart!')
    core.update_topic()
    core.state['dst'] = dst
