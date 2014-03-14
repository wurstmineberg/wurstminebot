import random

class Text:
    def __add__(self, other):
        if isinstance(other, str):
            other = LiteralText(other)
        return ConcatenatedText(self, other)
    
    def __init__(self, from_string, context=None):
        pass #TODO parse from_string
    
    def __or__(self, other):
        if isinstance(other, str):
            other = LiteralText(other)
        return RandomText(self, other)
    
    def __radd__(self, other):
        if isinstance(other, str):
            other = LiteralText(other)
        return ConcatenatedText(other, self)
    
    __ror__ = __or__
    
    def __str__(self):
        return self.to_string()
    
    def to_string(self, context=None, char_limit=None):
        return ''

class ConcatenatedText(Text):
    def __init__(self, left_text, right_text):
        self.left_text = left_text
        self.right_text = right_text
    
    def to_string(self, context=None, char_limit=None):
        #TODO try shorter left strings
        left_string = self.left_text.to_string(context=context, char_limit=char_limit)
        return left_string + self.right_text.to_string(context=context, char_limit=(None if char_limit is None else char_limit - len(left_string)))

class LiteralText(Text):
    def __init__(self, from_string):
        self.string = from_string
    
    def to_string(self, context=None, char_limit=None):
        if char_limit is not None and len(self.string) > char_limit:
            raise ValueError('the string ' + repr(self.string) + ' does not fit into the character limit of ' + repr(char_limit))
        return self.string

class RandomText(Text):
    def __init__(self, *args):
        self.choices = args
    
    def to_string(context=None, char_limit=None):
        choices = self.choices[:]
        random.shuffle(choices)
        for choice in choices:
            try:
                return choice.to_string(context=context, char_limit=char_limit)
            except ValueError:
                continue
        else:
            raise ValueError('none of the random texts fit into the character limit of ' + repr(char_limit))
