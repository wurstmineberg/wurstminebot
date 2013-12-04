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

def parseVersionString():
    try:
        with open('/opt/hub/wurstmineberg/wurstminebot/README.md') as readme:
            for line in readme.read().splitlines():
                if line.startswith('This is `wurstminebot` version'):
                    return line.split(' ')[4]
    except:
        pass

__version__ = str(parseVersionString())

from docopt import docopt
import json
import sys
import re

CONFIG_FILE = '/opt/wurstmineberg/config/people.json'
if __name__ == '__main__':
    arguments = docopt(__doc__, version='nicksub (wurstminebot ' + __version__ + ')')
    CONFIG_FILE = arguments['--config']

def config(person_id=None):
    try:
        with open(CONFIG_FILE) as config_file:
            j = json.load(config_file)
    except:
        j = []
    if person_id is None:
        return j
    for person in j:
        if person.get('id') == person_id:
            return person
    else:
        raise PersonNotFoundError('person with id ' + str(person_id) + ' not found')

def set_config(config_dict):
    with open(CONFIG_FILE, 'w') as config_file:
        json.dump(config_dict, config_file, sort_keys=True, indent=4, separators=(',', ': '))

def update_config(person_id, path, value=None, delete=False):
    config_dict = config()
    full_config_dict = config_dict
    for index, person in enumerate(config_dict):
        if person.get('id') == person_id:
            config_dict = config_dict[index]
    else:
        raise PersonNotFoundError('person with id ' + str(person_id) + ' not found')
    if len(path) > 1:
        for key in path[:-1]:
            if not isinstance(config_dict, dict):
                raise KeyError('Trying to update a non-dict config key')
            if key not in config_dict:
                config_dict[key] = {}
            config_dict = config_dict[key]
    if len(path) > 0:
        if delete:
            del config_dict[path[-1]]
        else:
            config_dict[path[-1]] = value
    else:
        if delete:
            del full_config_dict[index]
        else:
            full_config_dict[index] = value
    set_config(full_config_dict)

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
            raise TypeError('id or nick may not be None')
        if context is None:
            self.id = id_or_nick
            config(self.id) # raises PersonNotFoundError if the id is invalid
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
    
    def __eq__(self, other):
        return self.id == other.id
    
    @property
    def description(self):
        return config(self.id).get('description')
    
    @description.setter
    def description(self, value):
        update_config(self.id, ['description'], value=value)
    
    @description.deleter
    def description(self):
        update_config(self.id, ['description'], delete=True)
    
    def display_name(self):
        return self.id if self.name is None else self.name
    
    def invited(self):
        return self.whitelisted() or self.status == 'invited'
    
    def irc_nick(self, respect_highlight_option=True, channel_members=[], fallback=True):
        """Returns the best IRC nick for the person. “Best” in this case means the first in the list.
        
        respect_highlight_option: if this is True and the person has the chatsync_highlight option on, a zero-width non-joiner will be inserted after the first character of the nick.
        channel_members: if this is not empty, nicks in this list will be preferred.
        fallback: this defines how an empty list of IRC nicks is handled. If it is True, the display name will be used. If it is False, an AttributeError will be raised. For other values, the fallback will be returned instead.
        """
        for nick in self.irc_nicks:
            if nick in channel_members:
                break
        else:
            if len(self.irc_nicks) > 0:
                nick = self.irc_nicks[0]
            elif fallback is True:
                return self.display_name()
            elif fallback is False:
                raise AttributeError('Person has no IRC nicks')
            else:
                return fallback
        if respect_highlight_option and not self.option('chatsync_highlight'):
            return nick[0] + '\u200c' + nick[1:]
        return nick
    
    @property
    def irc_nicks(self):
        return config(self.id).get('irc', {}).get('nicks', [])
    
    @irc_nicks.setter
    def irc_nicks(self, value):
        update_config(self.id, ['irc', 'nicks'], value=value)
    
    @irc_nicks.deleter
    def irc_nicks(self):
        update_config(self.id, ['irc', 'nicks'], delete=True)
    
    @property
    def minecraft(self):
        return config(self.id).get('minecraft')
    
    @minecraft.setter
    def minecraft(self, value):
        update_config(self.id, ['minecraft'], value=value)
    
    @minecraft.deleter
    def minecraft(self):
        update_config(self.id, ['minecraft'], delete=True)
    
    @property
    def name(self):
        return config(self.id).get('name')
    
    @name.setter
    def name(self, value):
        update_config(self.id, ['name'], value=value)
    
    @name.deleter
    def name(self):
        update_config(self.id, ['name'], delete=True)
    
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
    
    @property
    def nicks(self):
        return config(self.id).get('nicks', [])
    
    @nicks.setter
    def nicks(self, value):
        update_config(self.id, ['nicks'], value=value)
    
    @nicks.deleter
    def nicks(self):
        update_config(self.id, ['nicks'], delete=True)
    
    @property
    def nickserv(self):
        return config(self.id).get('irc', {}).get('nickserv')
    
    @nickserv.setter
    def nickserv(self, value):
        update_config(self.id, ['irc', 'nickserv'], value=value)
    
    @nickserv.deleter
    def nickserv(self):
        update_config(self.id, ['irc', 'nickserv'], delete=True)
    
    def option(self, option_name):
        default_true_options = ['chatsync_highlight'] # These options are on by default. All other options are off by default.
        if str(option_name) in self.options:
            return self.options[str(option_name)]
        else:
            return str(option_name) in default_true_options
    
    @property
    def options(self):
        return config(self.id).get('options', {})
    
    @options.setter
    def options(self, value):
        update_config(self.id, ['options'], value=value)
    
    @options.deleter
    def options(self):
        update_config(self.id, ['options'], delete=True)
    
    def option_is_default(self, option_name):
        return str(option_name) not in self.options
    
    @property
    def reddit(self):
        return config(self.id).get('reddit')
    
    @reddit.setter
    def reddit(self, value):
        update_config(self.id, ['reddit'], value=value)
    
    @reddit.deleter
    def reddit(self):
        update_config(self.id, ['reddit'], delete=True)
    
    def reload(self):
        """Deprecated, properties are now loaded dynamically"""
        for person in config():
            if person.get('id') == self.id:
                break
        else:
            raise PersonNotFoundError('person with id ' + str(self.id) + ' not found')
    
    def set_option(self, option_name, value):
        opts = self.options
        opts[option_name] = value
        self.options = opts
    
    @property
    def status(self):
        return config(self.id).get('status', 'later')
    
    @status.setter
    def status(self, value):
        if value == 'later':
            del self.status
        else:
            update_config(self.id, ['status'], value=value)
    
    @status.deleter
    def status(self):
        update_config(self.id, ['status'], delete=True)
    
    @property
    def twitter(self):
        return config(self.id).get('twitter')
    
    @twitter.setter
    def twitter(self, value):
        update_config(self.id, ['twitter'], value=value)
    
    @twitter.deleter
    def twitter(self):
        update_config(self.id, ['twitter'], delete=True)
    
    @property
    def website(self):
        return config(self.id).get('website')
    
    @website.setter
    def website(self, value):
        update_config(self.id, ['website'], value=value)
    
    @website.deleter
    def website(self):
        update_config(self.id, ['website'], delete=True)
    
    def whitelisted(self):
        return self.status in ['founding', 'later', 'postfreeze']
    
    @property
    def wiki(self):
        return config(self.id).get('wiki')
    
    @wiki.setter
    def wiki(self, value):
        update_config(self.id, ['wiki'], value=value)
    
    @wiki.deleter
    def wiki(self):
        update_config(self.id, ['wiki'], delete=True)

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
