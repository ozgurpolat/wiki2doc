# pylint: disable=too-many-lines
"""
Unit tests
run here: (my-trac) (base) ozgur@debian:~/my-trac/my-plugins/wiki2doc_plugin$ python -m unittest tests.api
"""

import unittest
import logging
logging.basicConfig(level=logging.DEBUG, filename='test.log', filemode='w')
log = logging.getLogger()

from wiki2doc.wiki2doc import Wiki2Doc
from trac.test import EnvironmentStub, MockRequest
from datetime import datetime, timedelta
from trac.util.datefmt import utc
from trac.wiki import WikiPage
from trac.attachment import Attachment
from StringIO import StringIO
import tempfile
from mock import patch
from trac.wiki.web_ui import DefaultWikiPolicy, WikiModule
from wiki2doc.helpers import get_base_url, request_redirect
from trac.web.api import RequestDone
import os


def _insert_wiki_pages(env, pages):
    """ insert wiki pages """
    time = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
    for name, text in pages.iteritems():
        page = WikiPage(env)
        page.name = name
        page.text = text
        page.save('author', 'comment', time)

class Wiki2DocApiTestCase(unittest.TestCase): # pylint: disable=too-many-public-methods
    """ Tests for the basic wiki2doc api """

    def setUp(self):
        self.tktids = None
        self.gr_api = Wiki2Doc(EnvironmentStub()) # pylint: disable=too-many-function-args

        pages = {
                    'helloworld': """=Lorem ipsum dolor sit amet,
        consetetur sadipscing elitr, sed diam nonumy eirmod tempor
        [[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
        aliquyam erat, sed diam \n[[Image(Image2.jpg)])]\nvoluptua.""",
                    'attachments': """=Attachments"""}

        env = self.gr_api.env

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image_path below.

        _insert_wiki_pages(env, pages)
        spec = 'attachments'
        page = WikiPage(env, spec)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)

        path = os.getcwd()
        path = path + "/tests/resource/template.docx"
        data_template=open(path,"rb").read()
        attachment.insert("template.docx", StringIO(data_template), len(data_template))
        
        spec = 'helloworld'
        page = WikiPage(env, spec)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)

        path = os.getcwd()
        path = path + "/tests/resource/Image1.jpg"
        img1=open(path,"rb").read()
        # IMPORTANT: If you use "template.docx" instead of
        #            "Image1.jpg" below, it inserts the
        #            image inside "template.docx"
        attachment.insert("Image1.jpg", StringIO(img1), len(img1))

        path = os.getcwd()
        path = path + "/tests/resource/Image2.jpg"
        img2=open(path,"rb").read()
        attachment.insert("Image2.jpg", StringIO(img2), len(img2))

    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')

    def test_process_request(self):
        """ Test process_request method """

        #log.debug('pagename: {}, filename:{}'.format(pagename, filename))

        self.gr_api.errorlog = []
        
        # test template data for initial view
#         req = MockRequest(self.gr_api.env, method='GET',
#                           args={'create_report': u'Create Wiki Doc', 
#                                 '__FORM_TOKEN': u'a59a7f79fdf7bd881c7b4197', 
#                                 'get_doc_template': u'http://127.0.0.1:8000/attachment/wiki/Attachments/template.docx', 
#                                 'get_wiki_link': u'http://127.0.0.1:8000/wiki/helloworld'})
        req = MockRequest(self.gr_api.env, method='GET', args={})
        
        template, data, _ = Wiki2Doc.process_request(self.gr_api, req) # pylint: disable=unpacking-non-sequence
        log.debug('template; {}, data:{}'.format(template, data))
        
        self.assertEqual(template, "wiki2doc.html", "template")

        expected_data = {'form': {'create_report': u'Create Wiki Doc',
                                  '__FORM_TOKEN': u'a59a7f79fdf7bd881c7b4197',
                                  'get_doc_template': u'http://example.org/trac.cgi/attachment/wiki/attachments/template.docx',
                                  'get_wiki_link': u'http://example.org/trac.cgi/wiki/helloworld'}}

        log.debug('{}'.format(data))

        self.assertEqual(data,
                         expected_data,
                         "Dictionary data returned by " +\
                         "process_request does not match")

        get_doc_template = get_base_url(req) + u'attachment/wiki/attachments/template.docx'
        get_wiki_link = get_base_url(req) + u'wiki/helloworld'
        
        args = {'create_report': u'Create Wiki Doc',
                '__FORM_TOKEN': u'a59a7f79fdf7bd881c7b4197',
                'get_doc_template': get_doc_template,
                'get_wiki_link': get_wiki_link,}
        
        # test redirect
        req = MockRequest(self.gr_api.env, method='POST', args=args)
        #resp = WikiModule(self.gr_api.env).process_request(req)
        #log.debug('resp:{}'.format(resp))
        log.debug('dir(req):{}'.format(dir(req)))
        log.debug('req.headers_sent:{}'.format(req.headers_sent))
        log.debug('query_string:{}'.format(req.query_string))
        log.debug('path_info:{}'.format(req.path_info))
        log.debug('headers_sent:{}'.format(req.headers_sent))
        log.debug('redirect:{}'.format(req.redirect))
        log.debug('req.args:{}'.format(req.args))
 
        with patch('trac.web.api.Request.redirect') as mock_redirect:
            data = {}
            log.debug('req.args important: {}'.format(req.args))
            
            try:
                _, data, _ = Wiki2Doc.process_request(self.gr_api, req) # pylint: disable=unpacking-non-sequence
                
                log.debug('1. IMPORTANT data: {}'.format(data))
                req_redirect = request_redirect(req) # pylint: disable=unpacking-non-sequence
                log.debug('req_redirect{}'.format(req_redirect))
                mock_redirect.assert_called_once_with('/trac.cgi/wiki2doc?create_report=Create%20Wiki%20Doc&__FORM_TOKEN=a59a7f79fdf7bd881c7b4197&get_doc_template=http%3A//example.org/trac.cgi/attachment/wiki/attachments/template.docx&get_wiki_link=http%3A//example.org/trac.cgi/wiki/helloworld')
            except RequestDone:
                log.debug('IMPORTANT data: {}'.format(data))
                self.assertEqual(data, {}, "RequestDone returns error!")
            except TypeError:
                pass

if __name__ == '__main__':
    unittest.main()
