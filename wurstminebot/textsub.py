import random

class Text:
    def __add__(self, other):
        if isinstance(other, str):
            other = LiteralText(other)
        if isinstance(other, Text):
            return ConcatenatedText(self, other)
        else:
            return NotImplemented
    
    def __init__(self, from_string, context=None):
        pass #TODO parse from_string
    
    def __or__(self, other):
        if isinstance(other, str):
            other = LiteralText(other)
        if isinstance(other, Text):
            return RandomText(self, other)
        else:
            return NotImplemented
    
    def __radd__(self, other):
        if isinstance(other, str):
            other = LiteralText(other)
        if isinstance(other, Text):
            return ConcatenatedText(other, self)
        else:
            return NotImplemented
    
    __ror__ = __or__
    
    def __str__(self):
        return self.to_string()
    
    def to_string(self, context=None, char_limit=float('inf')):
        return ''
    
    def to_tellraw(self, default_color=None):
        if default_color is None:
            return self.to_string(context='minecraft')
        return {
            'color': default_color,
            'text': self.to_string(context='minecraft')
        }

class ConcatenatedText(Text):
    def __init__(self, *texts):
        self.texts = texts
    
    def to_string(self, context=None, char_limit=float('inf')):
        #TODO try shorter left strings
        ret = ''
        for text in self.texts:
            ret += text.to_string(context=context, char_limit=char_limit - len(ret))
        return ret
    
    def to_tellraw(self, default_color=None):
        ret = []
        for text in self.texts:
            tellraw_section = text.to_tellraw(default_color=default_color)
            if isinstance(tellraw_section, str):
                if default_color is None:
                    tellraw_section = {'text': tellraw_section}
                else:
                    tellraw_section = {
                        'color': default_color,
                        'text': tellraw_section
                    }
            if isinstance(tellraw_section, dict):
                tellraw_section = [tellraw_section]
            ret += tellraw_section
        return ret

class LiteralText(Text):
    def __init__(self, from_string):
        self.string = from_string
    
    def to_string(self, context=None, char_limit=float('inf')):
        if len(self.string) > char_limit:
            raise ValueError('the string ' + repr(self.string) + ' does not fit into the character limit of ' + repr(char_limit))
        return self.string

class RandomText(Text):
    def __init__(self, *args):
        self.choices = args
    
    def to_string(self, context=None, char_limit=float('inf')):
        choices = self.choices[:]
        random.shuffle(choices)
        for choice in choices:
            try:
                return choice.to_string(context=context, char_limit=char_limit)
            except ValueError:
                continue
        else:
            raise ValueError('none of the random texts fit into the character limit of ' + repr(char_limit))
    
    def to_tellraw(self, default_color=None):
        return random.choice(self.choices).to_tellraw(default_color=default_color)
