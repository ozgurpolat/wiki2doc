""" Helper methods. """

import re
#import docx
import urllib
from itertools import groupby
#from docx.shared import Inches
#from docx.shared import Pt
#from docx.oxml import OxmlElement
#from docx.oxml.ns import qn
#from __builtin__ import None

def get_base_url(req):
    """ Returns base url from the request object. """
    base_url = req.base_url
    url = r"https?://(.*)?"
    url_match = re.compile(url)
    match = url_match.match(base_url)
    if match:
        base_url = "http://" + str(match.group(1)) + "/"
        return base_url
