#!/usr/bin/env python3
"""Nickname substitution between Minecraft, Twitter, and other contexts.

Usage: 
  nicksub [options] [NICK]
  nicksub -h | --help
  nicksub --version

Options:
  -f, --from=SOURCE  Source environment [default: minecraft].
  -h, --help         Print this screen and exit.
  -t, --to=TARGET    Target environment [default: twitter].
  --config=<config>  Path to the config file [default: /opt/wurstmineberg/config/people.json].
  --exit-on-fail     Exit with status code 1 if the NICK cannot be found in the source environment, and exit with status code 2 if there is no equivalent nick in the target environment. Has no effect when NICK is omitted.
  --strict           Only match the first nick per environment.
  --version          Print version info and exit.
"""

__version__ = '2.6.0'

from docopt import docopt
import json
import sys
import re

CONFIG_FILE = '/opt/wurstmineberg/config/people.json'
if __name__ == '__main__':
    arguments = docopt(__doc__, version='nicksub (wurstminebot ' + __version__ + ')')
    CONFIG_FILE = arguments['--config']

def config():
    try:
        with open(CONFIG_FILE) as config_file:
            j = json.load(config_file)
    except:
        j = []
    return j

class PersonNotFoundError(Exception):
    pass # raised when a Person object is created or reloaded with data not in the config

def ircNicks(mode='all', include_ids=False):
    for person in config():
        if 'irc' in person and 'nicks' in person['irc'] and len(person['irc']['nicks']):
            if mode == 'all':
                for nick in person['irc']['nicks']:
                    yield (person['id'], nick) if include_ids else nick
            elif mode == 'lists':
                yield (person['id'], person['irc']['nicks']) if include_ids else person['irc']['nicks']
            elif mode == 'main':
                yield (person['id'], person['irc']['nicks'][0]) if include_ids else person['irc']['nicks'][0]
            else:
                raise ValueError('unknown mode: ' + str(mode))

def minecraftNicks(include_ids=False):
    for person in config():
        if 'minecraft' in person:
            yield (person['id'], person['minecraft']) if include_ids else person['minecraft']

def otherNicks(mode='all', include_ids=False):
    for person in config():
        if 'nicks' in person and len(person['nicks']):
            if mode == 'all':
                for nick in person['nicks']:
                    yield (person['id'], nick) if include_ids else nick
            elif mode == 'lists':
                yield (person['id'], person['nicks']) if include_ids else person['nicks']
            else:
                raise ValueError('unknown mode: ' + str(mode))

def redditNicks(include_ids=False, format='plain'):
    def _formatRedditNick(nick):
        if format == 'plain':
            return nick
        elif format == 'prefix':
            return '/u/' + nick
        elif format == 'url_long':
            return 'https://www.reddit.com/user/' + nick
        elif format == 'url_short':
            return 'https://reddit.com/u/' + nick
        else:
            raise ValueError('unknown format: ' + str(format))
    
    for person in config():
        if 'reddit' in person:
            yield (person['id'], _formatRedditNick(person['reddit'])) if include_ids else _formatRedditNick(person['reddit'])

def twitterNicks(include_ids=False, twitter_at_prefix=False):
    for person in config():
        if 'twitter' in person:
            formatted_nick = ('@' + person['twitter']) if twitter_at_prefix else person['twitter']
            yield (person['id'], formatted_nick) if include_ids else formatted_nick

class Person:
    def __init__(self, id_or_nick, context=None, strict=True):
        if id_or_nick is None:
            return
        if context is None:
            self.id = id_or_nick
        elif context == 'irc':
            for id, irc_nick in ircNicks(mode='all', include_ids=True):
                if irc_nick.lower() == id_or_nick.lower():
                    self.id = id
                    break
            else:
                raise PersonNotFoundError('person with IRC nick ' + str(id_or_nick) + ' not found')
        elif context == 'minecraft':
            for id, minecraft_nick in minecraftNicks(include_ids=True):
                if minecraft_nick.lower() == id_or_nick.lower():
                    self.id = id
                    break
            else:
                raise PersonNotFoundError()
        elif context == 'reddit':
            for id, reddit_nick in redditNicks(include_ids=True, format='plain'):
                if id_or_nick.startswith('/u/'):
                    id_or_nick = id_or_nick[len('/u/'):]
                if reddit_nick.lower() == id_or_nick.lower():
                    self.id = id
                    break
            else:
                raise PersonNotFoundError('person with reddit nick ' + str(id_or_nick) + ' not found')
        elif context == 'twitter':
            for id, twitter_nick in twitterNicks(include_ids=True, twitter_at_prefix=False):
                if id_or_nick.startswith('@'):
                    id_or_nick = id_or_nick[len('@'):]
                if twitter_nick.lower() == id_or_nick.lower():
                    self.id = id
                    break
            else:
                raise PersonNotFoundError('person with twitter nick ' + str(id_or_nick) + ' not found')
        else:
            raise ValueError('unknown context: ' + str(context))
        self.reload()
    
    def __eq__(self, other):
        return self.id == other.id
    
    def display_name(self):
        return self.id if self.name is None else self.name
    
    def invited(self):
        return self.whitelisted() or self.status == 'invited'
    
    def irc_nick(self, respect_highlight_option=True, channel_members=[]):
        for nick in self.irc_nicks:
            if nick in channel_members:
                break
        else:
            if len(self.irc_nicks) > 0:
                nick = self.irc_nicks[0]
            else:
                return self.display_name()
        if respect_highlight_option and not self.option('chatsync_highlight'):
            return ret[0] + '\u200c' + ret[1:]
        return ret
    
    def nick(self, context, default=None, twitter_at_prefix=False):
        if context == 'irc':
            return self.irc_nicks[0] if self.irc_nicks is not None and len(self.irc_nicks) else default
        elif context == 'minecraft':
            return default if self.minecraft is None else self.minecraft
        elif context == 'reddit':
            return default if self.reddit is None else self.reddit
        elif context == 'twitter':
            return default if self.twitter is None else (('@' + self.twitter) if twitter_at_prefix else self.twitter)
        else:
            return default
    
    def option(self, option_name):
        default_true_options = ['chatsync_highlight'] # These options are on by default. All other options are off by default.
        if str(option_name) in self.options:
            return self.options[str(option_name)]
        else:
            return str(option_name) in default_true_options
    
    def option_is_default(self, option_name):
        return str(option_name) not in self.options
    
    def reload(self):
        for person in config():
            if person.get('id') == self.id:
                self.description = person.get('description')
                self.irc_nicks = person.get('irc', {}).get('nicks', [])
                self.nickserv = person.get('irc', {}).get('nickserv')
                self.minecraft = person.get('minecraft')
                self.name = person.get('name')
                self.nicks = person.get('nicks', [])
                self.options = person.get('options', {})
                self.reddit = person.get('reddit')
                self.status = person.get('status', 'later')
                self.twitter = person.get('twitter')
                self.website = person.get('website')
                break
        else:
            raise PersonNotFoundError('person with id ' + str(self.id) + ' not found')
    
    def whitelisted(self):
        return self.status in ['founding', 'later', 'postfreeze']

def everyone():
    for person in config():
        if id in person:
            yield Person(person['id'])

def sub(nick, source, target, strict=True, exit_on_fail=False, twitter_at_prefix=True):
    if exit_on_fail:
        if nick is None:
            sys.exit(1)
        try:
            ret = Person(nick, source).nick(target, twitter_at_prefix=twitter_at_prefix)
            if ret is None:
                sys.exit(2)
            else:
                return ret
        except PersonNotFoundError:
            sys.exit(1)
    else:
        if nick is None:
            return None
        try:
            return Person(nick, source).nick(target, nick, twitter_at_prefix=twitter_at_prefix)
        except PersonNotFoundError:
            return nick

def textsub(text, source, target, strict=False):
    def _nicksForContext(context):
        if context == 'irc':
            mode = 'main' if strict else 'all'
            return reversed(list(ircNicks(include_ids=True, mode=mode)))
        elif context == 'minecraft':
            return minecraftNicks(include_ids=True)
        elif context == 'reddit':
            return redditNicks(include_ids=True)
        elif context == 'twitter':
            return twitterNicks(include_ids=True, twitter_at_prefix=True)
        else:
            return []
    
    text = text[:]
    for id, nick in _nicksForContext(source):
        if Person(id).nick(target):
            text = re.sub('(?<![0-9A-Za-z@])(' + re.sub('\\|', '\\|', nick) + ')(?![0-9A-Za-z])', Person(id).nick(target, twitter_at_prefix=True), text, flags=re.IGNORECASE)
    if not strict:
        for id, nick in otherNicks(include_ids=True, mode='all'):
            if Person(id).nick(target):
                text = re.sub('(?<![0-9A-Za-z@])(' + re.sub('\\|', '\\|', nick) + ')(?![0-9A-Za-z])', Person(id).nick(target, twitter_at_prefix=True), text, flags=re.IGNORECASE)
    return text

if __name__ == '__main__':
    if arguments['NICK']:
        print(sub(arguments['NICK'], arguments['--from'], arguments['--to'], strict=arguments['--strict'], exit_on_fail=arguments['--exit-on-fail']))
    else:
        for line in sys.stdin:
            print(textsub(line, arguments['--from'], arguments['--to'], strict=arguments['--strict']), end='')
