# Wiki2doc plugin

import re
import re
import urllib
from genshi.builder import tag
from trac.core import *
from trac.web import IRequestHandler
from trac.web.chrome import INavigationContributor, ITemplateProvider, add_stylesheet, Chrome
from trac.env import Environment
from trac.resource import Resource
from trac.wiki.model import WikiPage
from trac.attachment import Attachment
from trac.web.api import RequestDone
from trac.util.text import to_unicode
from trac.util import content_disposition
from helpers import get_base_url
from helpers import set_req_keys
from helpers import get_sections_with_tables
from helpers import get_base_url
from doc import Doc
import numpy as np
from trac.util.html import html
from HTMLParser import HTMLParser
from operator import itemgetter
#from simplemultiproject.model import SmpModel
from trac.env import open_environment
from trac.perm import IPermissionRequestor
from trac.util import content_disposition
from trac.util.text import to_unicode
from htmlentitydefs import name2codepoint
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from itertools import groupby
import sys
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF, renderPM
import os
from StringIO import StringIO


TEMPLATE_INSTANCE = 'req'
TEMPLATE_PAGE = 'attachments'
TEMPLATE_NAME = 'template.docx'
#TEMPLATE_NAME = 'template.docm'

class Wiki2Doc(Component):
    implements(INavigationContributor, ITemplateProvider, IRequestHandler)

    errorlog = []

    def __init__(self):
        """ grab the 3 environments """
        self.data = {}

    def set_data(self, req_keys):
        """ Set self.data that will be passed to
            the template."""

        #self.data = {
        #    'create_report': args[0],
        #    'form_token': args[1],
        #    'get_wiki_link': args[2],
        #}

        self.data['form'] = {
             'create_report': to_unicode(req_keys['create_report']),
             '__FORM_TOKEN': to_unicode(req_keys['__FORM_TOKEN']),
             'get_doc_template': to_unicode(req_keys['get_doc_template']),
             'get_wiki_link': to_unicode(req_keys['get_wiki_link']),
        }

    def set_default_data(self, req):
        """ Sets default self.data for
            the intial loading of wiki2doc."""

        get_doc_template = get_base_url(req) + u'attachment/wiki/attachments/template.docx'
        get_wiki_link = get_base_url(req) + u'wiki/metrics'
        
        req_keys = {'create_report': u'Create Wiki Doc',
                    '__FORM_TOKEN': u'a59a7f79fdf7bd881c7b4197',
                    'get_doc_template': get_doc_template,
                    'get_wiki_link': get_wiki_link,}
        
        self.set_data(req_keys)
        
        return req_keys

    # INavigationContributor methods
    def get_active_navigation_item(self, req):
        return 'wiki2doc'

    def get_navigation_items(self, req):
        yield ('mainnav', 'wiki2doc',
               tag.a('Wiki2Doc', href=req.href.wiki2doc()))

    # IRequestHandler methods
    def match_request(self, req):
        """Each IRequestHandler is called to match a web request.
        The first matching handler is then used to process the request.
        Matching a request usually means checking the req.path_info
        string (the part of the URL relative to the Trac root URL)
        against a specific string prefix or regular expression.
        """
        return re.match(r'/wiki2doc(?:_trac)?(?:/.*)?$', req.path_info)
    
    def process_request(self, req):
        """Process the request. Return a (template_name, data) pair,
        where data is a dictionary of substitutions for the Jinja2
        template (the template context, in Jinja2 terms).

        Optionally, the return value can also be a (template_name, data,
        metadata) triple, where metadata is a dict with hints for the
        template engine or the web front-end."""
        
        self.errorlog = []
        action = req.args.get('create_report', '__FORM_TOKEN')
        req_keys = set_req_keys(req)
        
        if all(x is None for x in req_keys):
            self.set_default_data(req)
        else:
            pass

        if req.method == 'POST':
            errorlog = []
 
            page_path = req.args.get('get_wiki_link')
 
            match_path = re.match(
                r"(http://|e:)(.*|/)wiki/(.*)",
                page_path)
 
            if match_path:
                page_name = re.split(r'\s+', match_path.group(3))
                page_name = page_name[0]
                page_name = page_name.split("|")
                page_name = page_name[0]
                page_name = urllib.unquote(page_name)
                #resource = Resource('wiki', page_name[0], 1)
                page = WikiPage(self.env, page_name)
                 
                if page.exists == True:
                    errorlog, content = self.process_document(page, req)
                else:
                    errorlog.append(("Page {} does not exist.".format(page.name), page.name))
 
                self.data['errorlog'] = errorlog
                  
                if len(errorlog) == 0:
                    self.data['form'] = {
                         'create_report': to_unicode(req_keys[0]),
                         '__FORM_TOKEN': to_unicode(req_keys[1]),
                         'get_doc_template': to_unicode(req_keys[2]),
                         'get_wiki_link': to_unicode(req_keys[3]),
                    }
                    
                    length = len(content)
                    req.send_response(200)
                    req.send_header(
                        'Content-Type',
                        'application/' + \
                        'vnd.' + \
                        'openxmlformats-officedocument.' +
                        'wordprocessingml.' +
                        'document')
                    if length is not None:
                         req.send_header('Content-Length', length)
                    req.send_header('Content-Disposition',
                                     content_disposition('attachment',
                                                         'out.docx'))
                    req.end_headers()
                    req.write(content)
                    raise RequestDone
        else:
            pass

        add_stylesheet(req, 'hw/css/wiki2doc.css')
        # This tuple is for Genshi (template_name, data, content_type)
        # Without data the trac layout will not appear.
        if hasattr(Chrome, 'add_jquery_ui'):
            Chrome(self.env).add_jquery_ui(req) # pylint: disable=no-member        
        return 'wiki2doc.html', self.data, None

    # ITemplateProvider methods
    # Used to add the plugin's templates and htdocs 
    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    def get_template(self, req):
        """ return path of standard auto report template """
          
        page_path = get_base_url(req) + 'wiki/' + TEMPLATE_PAGE
#         self.envs[TEMPLATE_INSTANCE].project_url +\
#             '/wiki/' + TEMPLATE_PAGE
  
        for attachment in Attachment.select(self.env, 'wiki', TEMPLATE_PAGE):
            if attachment.filename == TEMPLATE_NAME:
                return attachment.path
        self.errorlog.append(
            ("Attachment {} could not be found at {}.".\
             format(TEMPLATE_NAME, TEMPLATE_PAGE),
             page_path))
 
    def get_htdocs_dirs(self):
        """Return a list of directories with static resources (such as style
        sheets, images, etc.)
 
        Each item in the list must be a `(prefix, abspath)` tuple. The
        `prefix` part defines the path in the URL that requests to these
        resources are prefixed with.
 
        The `abspath` is the absolute path to the directory containing the
        resources on the local file system.
        """
        from pkg_resources import resource_filename
        return [('hw', resource_filename(__name__, 'htdocs'))]
    
    def process_document(self, page, req):
        """ process selected create apo and
            create report tasks."""
 
        document = self.create_document(req)
    
        if document != None:
            sections = self.get_sections_with_images(page, req)
            sections = get_sections_with_tables(sections)
            document.add_document(sections)
            return self.errorlog, document.get_content()
        else:
            return self.errorlog, None
     
    def create_document(self, req):
        """ Creates document class """

        args = []
 
        args = [self.get_template(req),
                self.env,
                self,
                req]

        try:
            document = Doc(args)
            return document
        except:
            self.errorlog.append(("Document could not be created due to unexpected error: {}.".format(sys.exc_info()[0]), req.args))

        return None

    def get_sections_with_images(self, page, req):
        """ given a page, returns a list of sections
            with attached images stored in a dictionary where key
            is the image file name in the page and value is the
            file path to that image """
 
        sections_with_imgs = []
        page_images = {}
        img_list = []
        path_list = []
        img_filename = None
        img_path = None
        image = re.compile(r'\s*\[\[Image\((.*(\.jpg|\.png|\.gif|\.svg))\)\]\]\s*')
 
        text = page.text
        # Adding a new line to the last line to ensure that
        # all lines are processes (especially if there are
        # tables  later in get_tables_in_text function
        text = text + '\n\n'

        svg_flag = False

        if text is not None:
            for line in text.splitlines():
                match = image.match(line)
                if match:
                    img_filename = match.group(1)
                    img_filename_list = img_filename.split(':')

                    # Handiling image from another page [[Image(wiki:Another_page:hello_world.jpg)]]
                    if len(img_filename_list) == 3:
                        img_filename = img_filename_list[2]                    
                        page_name = img_filename_list[1]                        
                        page = WikiPage(self.env, page_name)

                    img_path = \
                        self.get_image_file(img_filename,
                                            page,
                                            req)

                    if img_filename.endswith('.svg'):
                        svg_flag, \
                        svg_filename, \
                        img_filename, \
                        img_path = self.convert_svg(req,
                                                    page,
                                                    img_filename,
                                                    img_path,
                                                    'PNG')

                    if img_filename and img_path:
                        img_list.append(img_filename)
                        path_list.append(img_path)
        page_images = dict(zip(img_list, path_list))

        if svg_flag:
            png_file = svg_filename[0] + ".png"
            svg_file = svg_filename[0] + ".svg"
            text = re.sub(svg_file, png_file, text)

        sections_with_imgs.append([page.name, text, page_images])
        page_images = {}

        return sections_with_imgs

    def get_wikipage(self, page_name):
        """ return a wiki page """
 
        page = WikiPage(self.env, page_name)
        if page.exists:
            return page

    def get_image_file(self, filename, page, req):
        """ return path of image attachment """
        
        page_path = req.args.get('get_wiki_link')
 
        if page.exists:
            for attachment in Attachment.select(page.env,
                                                page.realm,
                                                page.resource.id):

                if attachment.filename == filename:
#                    path = str(attachment.path)
                    return attachment.path
            self.errorlog.append(
                ("Attachment image {} could not be found at {}".\
                 format(filename, page.resource.id),
                 page_path))
        else:
            self.errorlog.append(
                ("Page {} could not be found!".format(page.name),
                 page_path))
            
    def convert_svg(self, req, page, img_filename, img_path, fmt):
        
        svg_flag = True
        svg_filename = img_filename.split('.')

        drawing = svg2rlg(img_path)
        
        tmp_dir = os.path.join(os.getcwd(), "tmp")
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)
        fmt_path= os.path.join(tmp_dir, svg_filename[0] + ".png")
        renderPM.drawToFile(drawing, fmt_path, fmt=fmt)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)
        img_fmt=open(fmt_path,"rb").read()
        fmt_filename = svg_filename[0] + ".png"
        insert_flag = True
        for attachment in Attachment.select(page.env,
                                            page.realm,
                                            page.resource.id):

            if attachment.filename == fmt_filename:
                insert_flag = False
        if insert_flag:      
            attachment.insert(fmt_filename, StringIO(img_fmt), len(img_fmt))
        
        img_filename = fmt_filename
        img_path = \
            self.get_image_file(img_filename,
                                page,
                                req)
        return svg_flag, svg_filename, img_filename, img_path 
    