import sys

from wurstminebot import commands
from wurstminebot import core
import json
from wurstminebot import loops
import minecraft
from wurstminebot import nicksub
import random
import re
import threading
import traceback

def endMOTD(sender, headers, message):
    irc_config = core.config('irc')
    chans = set(irc_config.get('channels', []))
    if 'main_channel' in irc_config:
        chans.add(irc_config['main_channel'])
    if 'dev_channel' in irc_config:
        chans.add(irc_config['dev_channel'])
    if 'live_channel' in irc_config:
        chans.add(irc_config['live_channel'])
    for chan in chans:
        try:
            core.state['bot'].joinchan(chan)
        except:
            core.debug_print('Exception while joining channel ' + str(chan) + ':')
            if core.config('debug', False) or core.state.get('is_daemon', False):
                traceback.print_exc(file=sys.stdout)
    if irc_config.get('main_channel') is not None:
        core.state['bot'].say(irc_config['main_channel'], "aaand I'm back.")
    minecraft.tellraw({
        'text': "aaand I'm back.",
        'color': 'gold'
    })
    core.debug_print("aaand I'm back.")
    core.update_all()
    if core.state.get('input_loop') is None:
        core.state['input_loop'] = loops.InputLoop()
        core.state['input_loop'].start()

def error_not_chan_op(sender, headers, message):
    irc_config = core.config('irc')
    if 'main_channel' in irc_config:
        core.state['bot'].say(irc_config['main_channel'], random.choice([
            'To change the topic, I need to be a channel operator.',
            'op me pls',
            'i can has op?'
        ]))

def action(sender, headers, message):
    try:
        irc_config = core.config('irc')
        if sender == irc_config.get('nick', 'wurstminebot'):
            return
        if 'main_channel' in irc_config and headers[0] == irc_config['main_channel']:
            minecraft.tellraw([
                {
                    'text': '* ' + nicksub.sub(sender, 'irc', 'minecraft'),
                    'color': 'aqua',
                    'hoverEvent': {
                        'action': 'show_text',
                        'value': sender + ' in ' + headers[0]
                    },
                    'clickEvent': {
                        'action': 'suggest_command',
                        'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '
                    }
                },
                {
                    'text': ' '
                },
                {
                    'text': nicksub.textsub(message, 'irc', 'minecraft'),
                    'color': 'aqua'
                }
            ])
    except SystemExit:
        core.debug_print('Exit in ACTION')
        core.cleanup()
        raise
    except:
        core.debug_print('Exception in ACTION:')
        if core.config('debug', False) or core.state('is_daemon', False):
            traceback.print_exc(file=sys.stdout)

def bot():
    import ircbotframe
    ret = ircbotframe.ircBot(core.config('irc')['server'], core.config('irc')['port'], core.config('irc')['nick'], core.config('irc')['nick'], password=core.config('irc').get('password'), ssl=core.config('irc').get('ssl', False))
    ret.log_own_messages = False
    ret.bind('376', endMOTD)
    ret.bind('482', error_not_chan_op)
    ret.bind('ACTION', action)
    ret.bind('JOIN', join)
    ret.bind('PART', part)
    ret.bind('PRIVMSG', privmsg)
    return ret

def join(sender, headers, message):
    if len(headers):
        chan = headers[0]
    elif message is not None and len(message):
        chan = message
    else:
        return
    for person in nicksub.everyone():
        if person.minecraft is not None and person.option('sync_join_part'):
            minecraft.tellraw([
                {
                    'text': sender,
                    'color': 'yellow',
                    'clickEvent': {
                        'action': 'suggest_command',
                        'value': sender + ': '
                    }
                },
                {
                    'text': ' joined ' + chan,
                    'color': 'yellow'
                }
            ], player=person.minecraft)

def nick(sender, headers, message):
    if message is None or len(message) == 0:
        return
    for person in nicksub.everyone():
        if person.minecraft is not None and person.option('sync_nick_changes'):
            minecraft.tellraw([
                {
                    'text': sender + ' is now known as ',
                    'color': 'yellow'
                },
                {
                    'text': message,
                    'color': 'yellow',
                    'clickEvent': {
                        'action': 'suggest_command',
                        'value': message + ': '
                    }
                }
            ], player=person.minecraft)

def part(sender, headers, message):
    chans = headers[0].split(',')
    if len(chans) == 0:
        return
    elif len(chans) == 1:
        chans = chans[0]
    elif len(chans) == 2:
        chans = chans[0] + ' and ' + chans[1]
    else:
        chans = ', '.join(chans[:-1]) + ', and ' + chans[-1]
    for person in nicksub.everyone():
        if person.minecraft is not None and person.option('sync_join_part'):
            minecraft.tellraw({
                'text': sender + ' left ' + chans,
                'color': 'yellow'
            }, player=person.minecraft)

def privmsg(sender, headers, message):
    irc_config = core.config('irc')
    def botsay(msg):
        for line in msg.splitlines():
            core.state['bot'].say(irc_config['main_channel'], line)

    try:
        core.debug_print('[irc] <' + sender + '>' + (headers[0] if headers[0].startswith('#') else '') + ' ' + message)
        sender_person = nicksub.person_or_dummy(sender, context='irc')
        if sender == irc_config.get('nick'):
            if headers[0] == irc_config.get('dev_channel') and irc_config.get('dev_channel') != irc_config.get('main_channel'):
                # sync commit messages from dev to main
                core.state['bot'].say(irc_config.get('main_channel', '#wurstmineberg'), message)
            return # ignore self otherwise
        if sender in irc_config.get('ignore', []):
            return
        if headers[0].startswith('#'):
            if message.startswith(irc_config.get('nick', 'wurstminebot') + ': ') or message.startswith(irc_config['nick'] + ', '):
                cmd = message[len(irc_config.get('nick', 'wurstminebot')) + 2:].split(' ')
                if len(cmd):
                    try:
                        commands.run(cmd, sender=sender_person, context='irc', channel=headers[0])
                    except SystemExit:
                        core.debug_print('Exit in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to ' + str(headers[0]))
                        core.cleanup()
                        raise
                    except core.TwitterError as e:
                        core.state['bot'].say(headers[0], sender + ': Error ' + str(e.status_code) + ': ' + str(e))
                        core.debug_print('TwitterError ' + str(e.status_code) + ' in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to ' + str(headers[0]) + ':')
                        core.debug_print(json.dumps(e.errors, sort_keys=True, indent=4, separators=(',', ': ')))
                    except Exception as e:
                        core.state['bot'].say(headers[0], sender + ': Error: ' + str(e))
                        core.debug_print('Exception in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to ' + str(headers[0]) + ':')
                        if core.config('debug', False) or core.state.get('is_daemon', False):
                            traceback.print_exc(file=sys.stdout)
            elif re.match('![A-Za-z]', message):
                cmd = message[1:].split(' ')
                if len(cmd):
                    try:
                        commands.run(cmd, sender=sender_person, context='irc', channel=headers[0])
                    except SystemExit:
                        core.debug_print('Exit in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to ' + str(headers[0]))
                        core.cleanup()
                        raise
                    except core.TwitterError as e:
                        core.state['bot'].say(headers[0], sender + ': Error ' + str(e.status_code) + ': ' + str(e))
                        core.debug_print('TwitterError ' + str(e.status_code) + ' in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to ' + str(headers[0]) + ':')
                        core.debug_print(json.dumps(e.errors, sort_keys=True, indent=4, separators=(',', ': ')))
                    except Exception as e:
                        core.state['bot'].say(headers[0], sender + ': Error: ' + str(e))
                        core.debug_print('Exception in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to ' + str(headers[0]) + ':')
                        if core.config('debug', False) or core.state.get('is_daemon', False):
                            traceback.print_exc(file=sys.stdout)
            elif headers[0] == irc_config.get('main_channel'):
                if re.match('https?://(mojang\\.atlassian\\.net|bugs\\.mojang\\.com)/browse/[A-Z]+-[0-9]+', message):
                    minecraft.tellraw([
                        {
                            'text': '<' + sender_person.nick('minecraft') + '>',
                            'color': 'aqua',
                            'hoverEvent': {
                                'action': 'show_text',
                                'value': sender + ' in ' + headers[0]
                            },
                            'clickEvent': {
                                'action': 'suggest_command',
                                'value': sender_person.nick('minecraft') + ': '
                            }
                        },
                        {
                            'text': ' '
                        },
                        {
                            'text': message,
                            'color': 'aqua',
                            'clickEvent': {
                                'action': 'open_url',
                                'value': message
                            }
                        }
                    ])
                    try:
                        match = re.match('https?://(mojang\\.atlassian\\.net|bugs\\.mojang\\.com)/browse/([A-Z]+)-([0-9]+)', message)
                        project = match.group(2)
                        issue_id = int(match.group(3))
                        core.state['bot'].say(headers[0], core.paste_mojira(project, issue_id))
                        minecraft.tellraw(core.paste_mojira(project, issue_id, tellraw=True))
                    except SystemExit:
                        core.debug_print('Exit while pasting mojira ticket')
                        core.cleanup()
                        raise
                    except Exception as e:
                        core.state['bot'].say(headers[0], 'Error pasting mojira ticket: ' + str(e))
                        core.debug_print('Exception while pasting mojira ticket:')
                        if core.config('debug', False) or core.state.get('is_daemon', False):
                            traceback.print_exc(file=sys.stdout)
                elif re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/[0-9]+$', message):
                    minecraft.tellraw([
                        {
                            'text': '<' + sender_person.nick('minecraft') + '>',
                            'color': 'aqua',
                            'hoverEvent': {
                                'action': 'show_text',
                                'value': sender + ' in ' + headers[0]
                            },
                            'clickEvent': {
                                'action': 'suggest_command',
                                'value': sender_person.nick('minecraft') + ': '
                            }
                        },
                        {
                            'text': ' '
                        },
                        {
                            'text': message,
                            'color': 'aqua',
                            'clickEvent': {
                                'action': 'open_url',
                                'value': message
                            }
                        }
                    ])
                    try:
                        twid = re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/([0-9]+)$', message).group(1)
                        minecraft.tellraw(core.paste_tweet(twid, link=False, tellraw=True))
                        botsay(core.paste_tweet(twid, link=False, tellraw=False))
                    except SystemExit:
                        core.debug_print('Exit while pasting tweet')
                        core.cleanup()
                        raise
                    except core.TwitterError as e:
                        core.state['bot'].say(headers[0], 'Error ' + str(e.status_code) + ' while pasting tweet: ' + str(e))
                        core.debug_print('TwitterError ' + str(e.status_code) + ' while pasting tweet:')
                        core.debug_print(json.dumps(e.errors, sort_keys=True, indent=4, separators=(',', ': ')))
                    except Exception as e:
                        core.state['bot'].say(headers[0], 'Error while pasting tweet: ' + str(e))
                        core.debug_print('Exception while pasting tweet:')
                        if core.config('debug', False) or core.state.get('is_daemon', False):
                            traceback.print_exc(file=sys.stdout)
                else:
                    match = re.match('([a-z0-9]+:[^ ]+)(.*)$', message)
                    if match:
                        url, remaining_message = match.group(1, 2)
                        minecraft.tellraw([
                            {
                                'text': '<' + sender_person.nick('minecraft') + '>',
                                'color': 'aqua',
                                'hoverEvent': {
                                    'action': 'show_text',
                                    'value': sender + ' in ' + headers[0]
                                },
                                'clickEvent': {
                                    'action': 'suggest_command',
                                    'value': sender_person.nick('minecraft') + ': '
                                }
                            },
                            {
                                'text': ' '
                            },
                            {
                                'text': url,
                                'color': 'aqua',
                                'clickEvent': {
                                    'action': 'open_url',
                                    'value': url
                                }
                            },
                            {
                                'text': remaining_message,
                                'color': 'aqua'
                            }
                        ])
                    else:
                        minecraft.tellraw({
                            'text': '',
                            'extra': [
                                {
                                    'text': '<' + sender_person.nick('minecraft') + '>',
                                    'color': 'aqua',
                                    'hoverEvent': {
                                        'action': 'show_text',
                                        'value': sender + ' in ' + headers[0]
                                    },
                                    'clickEvent': {
                                        'action': 'suggest_command',
                                        'value': sender_person.nick('minecraft') + ': '
                                    }
                                },
                                {
                                    'text': ' '
                                },
                                {
                                    'text': nicksub.textsub(message, 'irc', 'minecraft'),
                                    'color': 'aqua'
                                }
                            ]
                        })
        else:
            cmd = message.split(' ')
            if len(cmd):
                try:
                    commands.run(cmd, sender=sender_person, context='irc')
                except SystemExit:
                    core.debug_print('Exit in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to query')
                    core.cleanup()
                    raise
                except core.TwitterError as e:
                    core.state['bot'].say(sender, + 'Error ' + str(e.status_code) + ': ' + str(e))
                    core.debug_print('TwitterError ' + str(e.status_code) + ' in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to query:')
                    core.debug_print(json.dumps(e.errors, sort_keys=True, indent=4, separators=(',', ': ')))
                except Exception as e:
                    core.state['bot'].say(sender, 'Error: ' + str(e))
                    core.debug_print('Exception in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to query:')
                    if core.config('debug', False) or core.state.get('is_daemon', False):
                        traceback.print_exc(file=sys.stdout)
    except SystemExit:
        core.debug_print('Exit in PRIVMSG')
        core.cleanup()
        raise
    except:
        core.debug_print('Exception in PRIVMSG:')
        if core.config('debug', False) or core.state.get('is_daemon', False):
            traceback.print_exc(file=sys.stdout)

def set_topic(channel, new_topic, force=False):
    if new_topic is None:
        new_topic = ''
    if force or channel not in core.state['irc_topics'] or core.state['irc_topics'][channel] != new_topic:
        core.state['bot'].topic(channel, new_topic)
        core.state['irc_topics'][channel] = new_topic
