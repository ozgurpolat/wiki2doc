from HTMLParser import HTMLParser

class DocumentHTMLParser(HTMLParser): # pylint: disable=too-many-public-methods
    """ Parses wikimarkup to html code string """
    def __init__(self, document, paragraph, html_code):
        HTMLParser.__init__(self)
        self.document = document
        self.paragraph = paragraph
        self.run = self.paragraph.add_run()
        self.feed(html_code)

    def handle_starttag(self, tag, attrs):
        self.run = self.paragraph.add_run()
        if tag == "em":
            self.run.italic = True
        if tag == "strong":
            self.run.bold = True
        if tag == "span" and attrs[0][0] == "class"\
            and attrs[0][1] == "underline":
            self.run.underline = True
        if tag == "sub":
            self.run.font.subscript = True
        if tag == "sup":
            self.run.font.superscript = True
        if tag == "del":
            self.run.font.strike = True
#         if tag == "tt":
#             self.run.add_text(u' ')
        if tag in ["br", "ul", "ol"]:
            self.run.add_break()
        if tag == "p":
            #self.run.add_break()
            pass

    def handle_endtag(self, tag):
        if tag in ["br", "li", "ul", "ol"]:
            self.run.add_break()
        self.run = self.paragraph.add_run()

    def handle_data(self, data):
        self.run.add_text(data.strip('\n'))

    def handle_entityref(self, name):
        code_point = unichr(name2codepoint[name])
        self.run.add_text(code_point)

    def handle_charref(self, name):
        if name.startswith('x'):
            char_ref = unichr(int(name[1:], 16))
        else:
            char_ref = unichr(int(name))
        self.run.add_text(char_ref)