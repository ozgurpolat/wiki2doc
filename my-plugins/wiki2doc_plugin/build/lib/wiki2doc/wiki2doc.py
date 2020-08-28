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
from helpers import get_tables_in_text 
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

        #print('DIR_req', dir(req))

        self.errorlog = []
        action = req.args.get('create_report', '__FORM_TOKEN')
        req_keys = set_req_keys(req)

        print('req keys', req_keys)
        print('action:', action)
        print('self.env', self.env)

        if req.method == 'POST':
            errorlog = []
            print('request is not:', req)
            print('request args:', req.args)
 
            page_path = req.args.get('get_wiki_link')
 
            print('page_path', page_path)
 
            match_path = re.match(
                r"(http://|e:)(.*|/)wiki/(.*)",
                page_path)
 
            if match_path:
                spec_name = re.split(r'\s+', match_path.group(3))
                spec_name = spec_name[0]
                spec_name = spec_name.split("|")
                spec_name = spec_name[0]
                spec_name = urllib.unquote(spec_name)
                print(spec_name)
                #resource = Resource('wiki', spec_name[0], 1)
                page = WikiPage(self.env, spec_name)
 
                print(page.name)
                print('dir(print(page))', dir(page))
                print('page.exists', page.exists)
                 
                if page.exists == True:
                    errorlog, content = self.process_document(page, req)
                    print('True errorlog', errorlog)
                else:
                    errorlog.append(("Page {} does not exist.".format(page.name), page.name))
                    print('False errorlog', errorlog)
                # select dropdowns in form
#                 keys = [project, igrmilestone,
#                         milestone, igrtask,
#                         ogrtask, clicked_button]
 
                self.data['errorlog'] = errorlog
                print('errorlog', errorlog)
                  
                if len(errorlog) == 0:
                    self.data['form'] = {
                         'create_report': to_unicode(req_keys[0]),
                         'form_token': to_unicode(req_keys[1]),
                         'get_wiki_link': to_unicode(req_keys[2]),
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
  
        print("get_template:")
        print(req)
          
        page_path = get_base_url(req) + 'wiki/' + TEMPLATE_PAGE
#         self.envs[TEMPLATE_INSTANCE].project_url +\
#             '/wiki/' + TEMPLATE_PAGE
  
        print("YES YES page_path", page_path)
        print('Att.select', Attachment.select(self.env, 'wiki', TEMPLATE_PAGE))
  
        for attachment in Attachment.select(self.env, 'wiki', TEMPLATE_PAGE):
            print('attachment.filename', attachment.filename, 'TEMPLATE_NAME', TEMPLATE_NAME)
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
 
         
         
        sections = self.get_images_in_text(page, req)
        print('1.sections', sections)
         
        #sections = np.array(sections)
         
        #print('shape', sections.shape)
         
        sections = get_tables_in_text(sections)
        print('2.sections', sections)
         
        document.add_document(sections)
        print('OK So far after document.add_document(sections)')
        return self.errorlog, document.get_content()
     
    def create_document(self, req):
        """ Creates document class """
 
        args = []
 
        print('self.get_template:', self.get_template(req))
 
        args = [self.get_template(req),
                self.env,
                self,
                req]
          
        document = Doc(args)
 
        return document
 
    def get_images_in_text(self, page, req):
        """ given a list of sections, returns a list of sections
            with attached images stored in a dictionary where key
            is the image file name in the spec and value is the
            file path to that image """
 
        sections_with_imgs = []
        spec_images = {}
        img_list = []
        path_list = []
        img_filename = None
        img_path = None
        image = re.compile(r'\s*\[\[Image\((.*(\.jpg|\.png|\.gif))\)\]\]\s*')
 
        text = page.text
        # Adding a new line to the last line to ensure that
        # all lines are processes (especially if there are
        # tables  later in get_tables_in_text function
        text = text + '\n\n'
        if text is not None:
            for line in text.splitlines():
                match = image.match(line)
                if match:
                    img_filename = match.group(1)
                    img_path = \
                        self.get_image_file(img_filename,
                                            page,
                                            req)
                    if img_filename and img_path:
                        img_list.append(img_filename)
                        path_list.append(img_path)
        spec_images = dict(zip(img_list, path_list))
        sections_with_imgs.append([page.name, text, spec_images])
        spec_images = {}
 
        return sections_with_imgs
 
    def get_wikipage(self, spec_name):
        """ return a wiki page """
 
        page = WikiPage(self.env, spec_name)
        if page.exists:
            return page
 
    def get_image_file(self, filename, page, req):
        """ return path of image attachment """
        
        print('YES get_image_file')
        
        page_path = req.args.get('get_wiki_link')
 
        if page.exists:
            for attachment in Attachment.select(page.env,
                                                page.realm,
                                                page.resource.id):
                
                print('attachment.filename ==? filename', attachment.filename, filename)
                
                if attachment.filename == filename:
#                    path = str(attachment.path)
                    return attachment.path
            self.errorlog.append(
                ("Attachment {} could not be found at {}".\
                 format(filename, page.resource.id),
                 page_path))
        else:
            self.errorlog.append(
                ("Page for the spec " +\
                 "{} could not be found!".format(page.name),
                 page_path))
    