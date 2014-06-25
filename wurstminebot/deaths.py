from datetime import date
import minecraft
from wurstminebot import nicksub
import re
from datetime import timezone

messages = [
    {
        'id': 'anvil',
        'regex': 'was squashed by a falling anvil'
    },
    {
        'id': 'cactus',
        'regex': 'was pricked to death'
    },
    {
        'id': 'cactusEscape',
        'regex': 'walked into a cactus whilst trying to escape (.+)'
    },
    {
        'id': 'arrow',
        'regex': 'was shot by arrow'
    },
    {
        'id': 'drowned',
        'regex': 'drowned'
    },
    {
        'id': 'drownedEscape',
        'regex': 'drowned whilst trying to escape (.+)'
    },
    {
        'id': 'explosion',
        'regex': 'blew up'
    },
    {
        'id': 'explosionCreeper',
        'regex': 'was blown up by Creeper'
    },
    {
        'id': 'explosionBy',
        'regex': 'was blown up by (.+)'
    },
    {
        'id': 'hitGround',
        'regex': 'hit the ground too hard'
    },
    {
        'id': 'highVoid',
        'regex': 'fell from a high place and fell out of the world'
    },
    {
        'id': 'highFinishedPlayer',
        'regex': 'fell from a high place and got finished off by (' + minecraft.regexes.player + ')'
    },
    {
        'id': 'high',
        'regex': 'fell from a high place'
    },
    {
        'id': 'highLadder',
        'regex': 'fell off a ladder'
    },
    {
        'id': 'highVines',
        'regex': 'fell off some vines'
    },
    {
        'id': 'highWater',
        'regex': 'fell out of the water'
    },
    {
        'id': 'hitGroundFire',
        'regex': 'fell into a patch of fire'
    },
    {
        'id': 'hitGroundCactus',
        'regex': 'fell into a patch of cacti'
    },
    {
        'id': 'doomedToFall',
        'regex': 'was doomed to fall'
    },
    {
        'id': 'doomedToFallPlayerUsing',
        'regex': 'was doomed to fall by (' + minecraft.regexes.player + ') using \\[(.+)\\]'
    },
    {
        'id': 'doomedToFallBy',
        'regex': 'was doomed to fall by (.+)'
    },
    {
        'id': 'arrowHighVines',
        'regex': 'was shot off some vines by (.+)'
    },
    {
        'id': 'arrowHighLadder',
        'regex': 'was shot off a ladder by (.+)'
    },
    {
        'id': 'explosionHigh',
        'regex': 'was blown from a high place by (.+)'
    },
    {
        'id': 'fire',
        'regex': 'went up in flames'
    },
    {
        'id': 'burn',
        'regex': 'burned to death'
    },
    {
        'id': 'burnBy',
        'regex': 'was burnt to a crisp whilst fighting (.+)'
    },
    {
        'id': 'fireBy',
        'regex': 'walked into a fire whilst fighting (.+)'
    },
    {
        'id': 'slainPlayerUsing',
        'regex': 'was slain by (' + minecraft.regexes.player + ') using \\[(.+)\\]'
    },
    {
        'id': 'slainUsing',
        'regex': 'was slain by (.+) using \\[(.+)\\]'
    },
    {
        'id': 'slainSilverfish',
        'regex': 'was slain by Silverfish'
    },
    {
        'id': 'slainZombie',
        'regex': 'was slain by Zombie'
    },
    {
        'id': 'slain',
        'regex': 'was slain by (.+)'
    },
    {
        'id': 'shotPlayerUsing',
        'regex': 'was shot by (' + minecraft.regexes.player + ') using \\[(.+)\\]'
    },
    {
        'id': 'shotPlayer',
        'regex': 'was shot by (' + minecraft.regexes.player + ')'
    },
    {
        'id': 'shot',
        'regex': 'was shot by (.+)'
    },
    {
        'id': 'fireball',
        'regex': 'was fireballed by (.+)'
    },
    {
        'id': 'lavaBy',
        'regex': 'tried to swim in lava to escape (.+)'
    },
    {
        'id': 'lava',
        'regex': 'tried to swim in lava'
    },
    {
        'id': 'generic',
        'regex': 'died'
    },
    {
        'id': 'finishedPlayerUsing',
        'regex': 'got finished off by (' + minecraft.regexes.player + ') using \\[(.+)\\]'
    },
    {
        'id': 'finishedUsing',
        'regex': 'got finished off by (.+) using \\[(.+)\\]'
    },
    {
        'id': 'magicPlayer',
        'regex': 'was killed by (' + minecraft.regexes.player + ') using magic'
    },
    {
        'id': 'magicBy',
        'regex': 'was killed by (.+) using magic'
    },
    {
        'id': 'magic',
        'regex': 'was killed by magic'
    },
    {
        'id': 'starved',
        'regex': 'starved to death'
    },
    {
        'id': 'wall',
        'regex': 'suffocated in a wall'
    },
    {
        'id': 'genericBy',
        'regex': 'was killed trying to hurt (.+)'
    },
    {
        'id': 'pummeledBy',
        'regex': 'was pummeled by (.+)'
    },
    {
        'id': 'void',
        'regex': 'fell out of the world'
    },
    {
        'id': 'voidBy',
        'regex': 'was knocked into the void by (.+)'
    },
    {
        'id': 'wither',
        'regex': 'withered away'
    }
] # http://minecraft.gamepedia.com/Server#Death_messages

class Death:
    def __init__(self, log_line, time=None):
        for death in messages:
            match = re.match('(' + minecraft.regexes.timestamp + '|' + minecraft.regexes.full_timestamp + ') \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') ' + death['regex'] + '$', log_line)
            if not match:
                continue
            # death
            self.id = death['id']
            if time is None:
                if match.group(1).startswith('['):
                    self.timestamp = minecraft.regexes.strptime(date.today(), match.group(1)).astimezone(timezone.utc) # not guaranteed to be accurate
                else:
                    self.timestamp = datetime.strptime(match.group(1) + ' +0000', '%Y-%m-%d %H:%M:%S %z') #TODO fix timezone handling
            else:
                self.timestamp = time
            self.person = nicksub.person_or_dummy(match.group(2), context='minecraft')
            self.partial_message = log_line[len('[00:00:00] [Server thread/INFO]: ' + self.person.nick('minecraft') + ' '):]
            self.groups = match.groups()[2:]
            break
        else:
            raise ValueError('Log line is not a death')
    
    def irc_message(self, tweet_info=None, respect_highlight_option=True):
        victim_irc = self.person.irc_nick(respect_highlight_option=respect_highlight_option)
        return victim_irc + ' ' + nicksub.textsub(self.partial_message, 'minecraft', 'irc', strict=True) + ('' if tweet_info is None else ' [' + str(tweet_info) + ']')
    
    def log(self, file_obj=None):
        log_message = self.timestamp.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + ' ' + self.message()
        if file_obj is None:
            print(log_message)
        else:
            print(log_message, file=file_obj)
    
    def message(self):
        return (self.person.nick('minecraft')) + ' ' + self.partial_message
    
    def tweet(self, comment=None):
        victim_twitter = self.person.nick('twitter', twitter_at_prefix=True)
        status = '[DEATH] ' + victim_twitter + ' ' + nicksub.textsub(self.partial_message, 'minecraft', 'twitter', strict=True)
        if comment is not None and len(status + ' … ' + comment) <= 140:
            status += ' … ' + comment
        return status
