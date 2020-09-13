# pylint: disable=too-many-lines
"""
Unit tests
run here: (my-trac) (base) ozgur@debian:~/my-trac/my-plugins/wiki2doc_plugin$ python -m unittest tests.api
"""

import unittest
import logging
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
from wiki2doc.helpers import get_base_url
from wiki2doc.helpers import request_redirect
from wiki2doc.helpers import get_sections_with_tables
from trac.web.api import RequestDone
import os
from wiki2doc.helpers import check_for_relative_link


logging.basicConfig(level=logging.DEBUG, filename='test.log', filemode='w')
log = logging.getLogger()

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
        pagename = 'attachments'
        page = WikiPage(env, pagename)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)

        path = os.getcwd()
        path = path + "/tests/resource/template.docx"
        data_template=open(path,"rb").read()
        attachment.insert("template.docx", StringIO(data_template), len(data_template))
        
        pagename = 'helloworld'
        page = WikiPage(env, pagename)
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

        self.gr_api.errorlog = []

        req = MockRequest(self.gr_api.env, method='GET', args={})
        
        template, data, _ = Wiki2Doc.process_request(self.gr_api, req) # pylint: disable=unpacking-non-sequence
        
        self.assertEqual(template, "wiki2doc.html", "template")

        expected_data = {'form': {'create_report': u'Create Wiki Doc',
                                  '__FORM_TOKEN': u'a59a7f79fdf7bd881c7b4197',
                                  'get_doc_template': u'http://example.org/trac.cgi/attachment/wiki/attachments/template.docx',
                                  'get_wiki_link': u'http://example.org/trac.cgi/wiki/helloworld'}}

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
 
        with patch('trac.web.api.Request.redirect') as mock_redirect:

            data = {}
            
            try:
                _, data, _ = Wiki2Doc.process_request(self.gr_api, req) # pylint: disable=unpacking-non-sequence
                
                req_redirect = request_redirect(req) # pylint: disable=unpacking-non-sequence
                mock_redirect.assert_called_once_with('/trac.cgi/wiki2doc?' +\
                                                      'create_report=Create%20Wiki%20Doc&' +\
                                                      '__FORM_TOKEN=a59a7f79fdf7bd881c7b4197&' +\
                                                      'get_doc_template=http%3A//example.org/' +\
                                                      'trac.cgi/attachment/wiki/attachments/' +\
                                                      'template.docx&get_wiki_link=http%3A//' +\
                                                      'example.org/trac.cgi/wiki/helloworld')
            except RequestDone:
                self.assertEqual(data, {}, "RequestDone returns error!")
            except TypeError:
                pass

    def test_get_template(self):
        """ Test get_template method """
    
        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.env
        
        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # expected_path below.
    
        req = MockRequest(env)
    
        pagename = 'attachments'
        with env.db_transaction as dtb:
            dtb("INSERT INTO wiki (name,version) VALUES ('{}',2)".format(pagename))
        
        attachment = Attachment(env, 'wiki', pagename)
    
        path = os.getcwd()
        path = path + "/tests/resource/template.docx"
        data_template=open(path,"rb").read()
        attachment.insert("template.docx", StringIO(data_template), len(data_template))
    
        template_name = 'template_v2.docx'
        
        returned_path = self.gr_api.get_template(req)
        returned_path_split = returned_path.split("/")
        
        # Every time the test is executed, a random code is generated
        # we are getting this code to construct expected path
        random_code = returned_path_split[2].split("-")
        
        expected_path = unicode(env.path, "utf-8")[0:-6] + random_code[-1] + \
                        u'/files/attachments/wiki/05c/' +\
                        u'05cb34b44f3c96dbbba062f4392edaca659a46ed/' +\
                        u'12d4f1ceff58f7bc86893db034b5a338369368c5.docx'
        
        errorlog = []
    
        self.assertEqual(returned_path,
                         expected_path,
                         "expected_path for the template.docx does not match")
    
        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.env
        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image_path below.
    
        pagename = 'attachments'
        with env.db_transaction as dtb:
            dtb("DELETE FROM wiki")
            dtb("VACUUM")
            dtb("INSERT INTO wiki (name,version) VALUES ('{}',2)".format(pagename))
    
        attachment = Attachment(env, 'wiki', pagename)
    
        errorlog = []
    
        self.gr_api.get_template(req)
    
        self.assertEqual(self.gr_api.errorlog,
                         errorlog,
                         "Errorlog is not empty!")
    
    def test_request_redirect(self):
        """ Test request_redirect method """

        # test redirect
        req = MockRequest(self.gr_api.env)

        get_doc_template = get_base_url(req) + u'attachment/wiki/attachments/template.docx'
        get_wiki_link = get_base_url(req) + u'wiki/helloworld'

        args = {'create_report': u'Create Wiki Doc',
                '__FORM_TOKEN': u'a59a7f79fdf7bd881c7b4197',
                'get_doc_template': get_doc_template,
                'get_wiki_link': get_wiki_link,}
    
        req = MockRequest(self.gr_api.env, method='POST', args=args)

        with patch('trac.web.api.Request.redirect'):
            try:
                req_redirect = request_redirect(req) # pylint: disable=unpacking-non-sequence
    
                self.assertEqual(req_redirect,
                                 True,
                                 "Request redirect returns False!")
            except RequestDone:
                pass
            except TypeError:
                pass

    def test_get_wikipage(self):
        """ Test get_wikipage """

        env = self.gr_api.env

        pages = {
            'Specname1': """=Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
aliquyam erat, sed diam \n[[Image(Image2.jpg)])]\nvoluptua.""",
            'Specname2': """=Lorem ipsum dolor sit amet,
[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita 
[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet."""}

        _insert_wiki_pages(env, pages)

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image_path below.

        page_name = 'Specname1'
        page = self.gr_api.get_wikipage(page_name)

        page_text = pages['Specname1']

        self.assertEqual(page.text,
                         page_text,
                         "Returned page text does not match")

    def test_get_image_file(self):
        """ Test get_image_file 
            get_image_file(self, filename, page, req) """

        pages = {
            'Page1': """=Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
aliquyam erat, sed diam \n[[Image(Image2.jpg)])]\nvoluptua.""",
            'Page2': """=Lorem ipsum dolor sit amet,
[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita 
[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet."""}

        _insert_wiki_pages(self.gr_api.env, pages)

        pages = [
            [2,
             'Page1',
             'consetetur sadipscing elitr, sed diam nonumy eirmod tempor\n' +\
             '[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna \n' +\
            'aliquyam erat, sed diam \n[[Image(Image2.jpg)]]\nvoluptua.\n'],
            [3,
             'Page2',
             '[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita \n' +\
             '[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata \n' +\
             'sanctus est Lorem ipsum dolor sit amet.\n']]

        env = self.gr_api.env

        req = MockRequest(self.gr_api.env, method='GET', args={})

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image_path below.

        pagename = 'Page1'
        page1 = WikiPage(env, pagename)
        attachment = Attachment(page1.env,
                                page1.realm,
                                page1.resource.id)

        path = os.getcwd()
        path = path + "/tests/resource/Image1.jpg"
        img1=open(path,"rb").read()

        path = os.getcwd()
        path = path + "/tests/resource/Image2.jpg"
        img2=open(path,"rb").read()    

        # IMPORTANT: If you use "template.docx" instead of
        #            "Image1.jpg" below, it inserts the
        #            image inside "template.docx"
        attachment.insert("Image1.jpg", StringIO(img1), len(img1))
        attachment.insert("Image2.jpg", StringIO(img2), len(img2))

        pagename = 'Page2'
        page2 = WikiPage(env, pagename)
        attachment = Attachment(page2.env,
                                page2.realm,
                                page2.resource.id)

        path = os.getcwd()
        path = path + "/tests/resource/Image1.jpg"
        img1=open(path,"rb").read()

        path = os.getcwd()
        path = path + "/tests/resource/Image2.jpg"
        img2=open(path,"rb").read()

        # IMPORTANT: If you use "template.docx" instead of
        #            "Image1.jpg" below, it inserts the
        #            image inside "template.docx"
        attachment.insert("Image1.jpg", StringIO(img1), len(img1))
        attachment.insert("Image2.jpg", StringIO(img2), len(img2))

        filename = 'Image1.jpg'
        returned_path = self.gr_api.get_image_file(filename,
                                                   page1,
                                                   req)

        returned_path_split = returned_path.split("/")

        # Every time the test is executed, a random code is generated
        # we are getting this code to construct expected path
        random_code = returned_path_split[2].split("-")

        image_path1 = unicode(env.path, "utf-8")[0:-6] + random_code[-1] + \
            u'/files/attachments/wiki/3f0/3f076c5ef9351e9197b499926955d8d481454993/98c78c01ccdb21a78fd4f561e980ccd4d3a5a685.jpg'

        self.assertEqual(returned_path,
                         image_path1,
                         "Returned image_path value does not match" +\
                         " for filename:{}!".format(filename))
 
        filename = 'Image2.jpg'
        returned_path = self.gr_api.get_image_file(filename,
                                                   page2,
                                                   req)

        returned_path_split = returned_path.split("/")

        # Every time the test is executed, a random code is generated
        # we are getting this code to construct expected path
        random_code = returned_path_split[2].split("-")

        image_path2 = unicode(env.path, "utf-8")[0:-6] +\
            random_code[-1] + \
            u'/files/attachments/wiki/b43/' +\
            u'b43b4133f4d1cd7ff1628609fa507e853760133b/' +\
            u'e8385af6dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'

        self.assertEqual(returned_path,
                         image_path2,
                         "Returned image_path value does not match" +\
                         " for filename:{}!".format(filename))
 
        self.gr_api.errorlog = []
        filename = 'Image1.jpg'
        pagename = 'Page3'
        page3 = WikiPage(env, pagename)

        self.gr_api.get_image_file(filename, page3, req)
 
        errorlog = [('Page Page3 could not be found!', None)]
 
        self.assertEqual(self.gr_api.errorlog,
                         errorlog,
                         "Errorlog does not match for " +\
                         "page: {}".format(pagename))
 
        self.gr_api.errorlog = []
        filename = 'Image4.jpg'
        self.gr_api.get_image_file(filename, page2, req)
        errorlog = [('Attachment image Image4.jpg could not be found at Page2', None)]

        self.assertEqual(self.gr_api.errorlog,
                         errorlog,
                         "Errorlog does not match for page: {}".format(page2.name))


    def test_check_for_relative_link(self):
        """ Test check_for_relative_link """

        hypermatches = [('', '../', 'GDL/Images',
                         '|DT-GDL]]', 'DT-GDL'),
                        ('', '../', 'GDL/Downloads',
                         '|FH-GDL]]', 'FH-GDL'),
                        ('', '../', 'GDL/Desktop',
                         '|MS-GDL]]', 'MS-GDL'),
                        ('', '../', 'GDL/Documents',
                         '|MBJ-GDL]]', 'MBJ-GDL')]

        hyperlists = check_for_relative_link(hypermatches)

        exp_hyperlists = [('', '', 'GDL/Images',
                           '|DT-GDL]]', 'DT-GDL'),
                          ('', '', 'GDL/Downloads',
                           '|FH-GDL]]', 'FH-GDL'),
                          ('', '', 'GDL/Desktop',
                           '|MS-GDL]]', 'MS-GDL'),
                          ('', '', 'GDL/Documents',
                           '|MBJ-GDL]]', 'MBJ-GDL')]

        self.assertEqual(
            hyperlists,
            exp_hyperlists,
            "list of hypermatches do not match!")

        hypermatches = [('', '../test', 'GDL/Images',
                         '|DT-GDL]]', 'DT-GDL'),
                        ('', '../test/test2', 'GDL/Downloads',
                         '|FH-GDL]]', 'FH-GDL'),
                        ('', '../$data/test', 'GDL/Desktop',
                         '|MS-GDL]]', 'MS-GDL'),
                        ('', '../http://', 'GDL/Documents',
                         '|MBJ-GDL]]', 'MBJ-GDL')]

        hyperlists = check_for_relative_link(hypermatches)

        exp_hyperlists = [('', 'test', 'GDL/Images',
                           '|DT-GDL]]', 'DT-GDL'),
                          ('', 'test/test2', 'GDL/Downloads',
                           '|FH-GDL]]', 'FH-GDL'),
                          ('', '$data/test', 'GDL/Desktop',
                           '|MS-GDL]]', 'MS-GDL'),
                          ('', 'http://', 'GDL/Documents',
                           '|MBJ-GDL]]', 'MBJ-GDL')]

        for i, hyper in enumerate(hyperlists):
            self.assertEqual(
                hyper[1],
                exp_hyperlists[i][1],
                "hyperlists do not match!")

        self.assertEqual(
            hyperlists,
            exp_hyperlists,
            "list of hypermatches do not match!")

        hypermatches = [('', '../', 'GDL/Images',
                         '|DT-GDL]]', 'DT-GDL')]

        hyperlist = check_for_relative_link(hypermatches)

        exp_hyperlist = [('', '', 'GDL/Images',
                          '|DT-GDL]]', 'DT-GDL')]

        self.assertEqual(
            hyperlist,
            exp_hyperlist,
            "hypermatches do not match!")

        # TESTING TO SEE IF hypermatches list
        # REMAINS THE SAME IF "../" NOT FOUND
        hypermatches = [(" '''Lorem ipsum''', **dolor** sit amet, Ref1 ",
                         'Dummy-AA-Database/',
                         'GDL/Desktop', '| MS-GDL]]', ' MS-GDL'),
                        (' consetetur [=#Fig8] sadipscing elitr, L, LT or ST ',
                         '/', 'GDL/Desktop',
                         '| MS-GDL]]', ' MS-GDL'),
                        ("  sed diam **A',,yz,,**nonumy ", 'GDL/',
                         'Desktop', '| MS-GDL]]', ' MS-GDL'),
                        (' eirmod  ', 'BR]] [[/',
                         'IP006/Dummy-AA-Database/GDL/Desktop',
                         '| MS-GDL]]', ' MS-GDL'),
                        ('tempor invidunt [=#Table5] ut labore' +\
                         ' et dolore magna aliquyam erat tempor invidunt ',
                         'IP006/', 'Dummy-AA-Database/GDL/Desktop',
                         '| MS-GDL]]', ' MS-GDL'),
                        (' ', '/', 'GDL/Desktop',
                         '| MS-GDL]]', ' MS-GDL'),
                        (', ut labore ', '/', 'GDL/Desktop',
                         '| MS-GDL]]', ' MS-GDL')]

        exp_hypermatches = check_for_relative_link(hypermatches)

        self.assertEqual(
            hypermatches,
            exp_hypermatches,
            "hypermatches do not match!")

    def test_get_sections_with_images(self):
        """ Test get_sections_with_images and
        get_image_file """

        pages = {
            'Page1': """=Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
aliquyam erat, sed diam \n[[Image(Image2.jpg)]]\nvoluptua.""",
            'Page2': """=Lorem ipsum dolor sit amet,
[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita 
[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet."""}

        _insert_wiki_pages(self.gr_api.env, pages)

        env = self.gr_api.env

        req = MockRequest(self.gr_api.env, method='GET', args={})

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image_path below.

        pagename1 = 'Page1'
        page1 = WikiPage(env, pagename1)
        attachment1 = Attachment(page1.env,
                                page1.realm,
                                page1.resource.id)

        path1 = os.getcwd()
        path1 = path1 + "/tests/resource/Image1.jpg"
        img1=open(path1,"rb").read()

        path2 = os.getcwd()
        path2 = path2 + "/tests/resource/Image2.jpg"
        img2=open(path2,"rb").read()    

        # IMPORTANT: If you use "template.docx" instead of
        #            "Image1.jpg" below, it inserts the
        #            image inside "template.docx"
        attachment1.insert("Image1.jpg", StringIO(img1), len(img1))
        attachment1.insert("Image2.jpg", StringIO(img2), len(img2))

        pagename2 = 'Page2'
        page2 = WikiPage(env, pagename2)
        attachment2 = Attachment(page2.env,
                                page2.realm,
                                page2.resource.id)

        # IMPORTANT: If you use "template.docx" instead of
        #            "Image1.jpg" below, it inserts the
        #            image inside "template.docx"
        attachment2.insert("Image1.jpg", StringIO(img1), len(img1))
        attachment2.insert("Image2.jpg", StringIO(img2), len(img2))

        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image dictionary below.
        filename1 = 'Image1.jpg'
        returned_path1 = self.gr_api.get_image_file(filename1,
                                                    page1,
                                                    req)

        returned_path1_split = returned_path1.split("/")

        # Every time the test is executed, a random code is generated
        # we are getting this code to construct expected path
        random_code1 = returned_path1_split[2].split("-")

        image_path1 = unicode(env.path, "utf-8")[0:-6] + \
            random_code1[-1] + \
            u'/files/attachments/wiki/3f0/' +\
            u'3f076c5ef9351e9197b499926955d8d481454993/' +\
            u'98c78c01ccdb21a78fd4f561e980ccd4d3a5a685.jpg'

        filename2 = 'Image2.jpg'
        returned_path2 = self.gr_api.get_image_file(filename2,
                                                    page2,
                                                    req)

        returned_path2_split = returned_path2.split("/")

        # Every time the test is executed, a random code is generated
        # we are getting this code to construct expected path
        random_code2 = returned_path2_split[2].split("-")

        image_path2 = unicode(env.path, "utf-8")[0:-6] +\
            random_code2[-1] + \
            u'/files/attachments/wiki/3f0/' +\
            u'3f076c5ef9351e9197b499926955d8d481454993/' +\
            u'e8385af6dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'

        expected_page = [['Page1', u'=Lorem ipsum dolor sit amet,' +\
                          u'\nconsetetur sadipscing elitr,' +\
                          u' sed diam nonumy eirmod tempor\n' +\
                          u'[[Image(Image1.jpg)]]\ninvidunt ut ' +\
                          u'labore et dolore magna \naliquyam ' +\
                          u'erat, sed diam \n[[Image(Image2.jpg)]]' +\
                          u'\nvoluptua.\n\n',
                          {u'Image1.jpg': image_path1, u'Image2.jpg': image_path2}]]

        self.assertEqual(
            self.gr_api.get_sections_with_images(page1, req),
            expected_page,
            "Extracted spec sections with images do not match!")

    def test_get_sections_with_tables(self):
        """ Test get_sections_with_tables and
        tables_in_spec_text """

        pages = {
            'Page1': """=Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
aliquyam erat, sed diam \n[[Image(Image2.jpg)]]\nvoluptua.
|| 1 || 2 || 3 ||
|||| 1-2 || 3 ||
|| 1 |||| 2-3 ||
|||||| 1-2-3 ||
=Lorem ipsum consetetur sadipscing elitr,""",
            'Page2': """=Lorem ipsum dolor sit amet,
|| 1 || 2 || 3 ||
|||| 1-2 || 3 ||
|| 1 |||| 2-3 ||
|||||| 1-2-3 ||
[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita 
[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet.
=Lorem ipsum consetetur sadipscing elitr,"""}

        _insert_wiki_pages(self.gr_api.env, pages)

        env = self.gr_api.env

        req = MockRequest(self.gr_api.env, method='GET', args={})

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image_path below.

        pagename1 = 'Page1'
        page1 = WikiPage(env, pagename1)
        attachment1 = Attachment(page1.env,
                                page1.realm,
                                page1.resource.id)

        path1 = os.getcwd()
        path1 = path1 + "/tests/resource/Image1.jpg"
        img1=open(path1,"rb").read()

        path2 = os.getcwd()
        path2 = path2 + "/tests/resource/Image2.jpg"
        img2=open(path2,"rb").read()    

        # IMPORTANT: If you use "template.docx" instead of
        #            "Image1.jpg" below, it inserts the
        #            image inside "template.docx"
        attachment1.insert("Image1.jpg", StringIO(img1), len(img1))
        attachment1.insert("Image2.jpg", StringIO(img2), len(img2))

        pagename2 = 'Page2'
        page2 = WikiPage(env, pagename2)
        attachment2 = Attachment(page2.env,
                                page2.realm,
                                page2.resource.id)

        # IMPORTANT: If you use "template.docx" instead of
        #            "Image1.jpg" below, it inserts the
        #            image inside "template.docx"
        attachment2.insert("Image1.jpg", StringIO(img1), len(img1))
        attachment2.insert("Image2.jpg", StringIO(img2), len(img2))

        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image dictionary below.
        filename1 = 'Image1.jpg'
        returned_path1 = self.gr_api.get_image_file(filename1,
                                                    page1,
                                                    req)

        returned_path1_split = returned_path1.split("/")

        # Every time the test is executed, a random code is generated
        # we are getting this code to construct expected path
        random_code1 = returned_path1_split[2].split("-")

        image_path1 = unicode(env.path, "utf-8")[0:-6] + \
            random_code1[-1] + \
            u'/files/attachments/wiki/b43/' +\
            u'b43b4133f4d1cd7ff1628609fa507e853760133b/' +\
            u'98c78c01ccdb21a78fd4f561e980ccd4d3a5a685.jpg'

        filename2 = 'Image2.jpg'
        returned_path2 = self.gr_api.get_image_file(filename2,
                                                    page2,
                                                    req)

        returned_path2_split = returned_path2.split("/")

        # Every time the test is executed, a random code is generated
        # we are getting this code to construct expected path
        random_code2 = returned_path2_split[2].split("-")

        image_path2 = unicode(env.path, "utf-8")[0:-6] +\
            random_code2[-1] + \
            u'/files/attachments/wiki/b43/' +\
            u'b43b4133f4d1cd7ff1628609fa507e853760133b/' +\
            u'e8385af6dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'

        sections = self.gr_api.get_sections_with_images(page2, req)
        log.debug('sections: {}'.format(sections))
        
        returned_sections = get_sections_with_tables(sections)

        expected_sections = [['Page2',
          u'=Lorem ipsum dolor sit amet,\n[[Table(Table_11.tbl)]]\n' +\
          u'[[Image(Image1.jpg)]]\n\nduo dolores et ea rebum. Stet ' +\
          u'clita \n[[Image(Image2.jpg)]]\nkasd gubergren, no sea ' +\
          u'takimata \nsanctus est Lorem ipsum dolor sit amet.\n' +\
          u'=Lorem ipsum consetetur sadipscing elitr,\n\n',
          {u'Image1.jpg': image_path1, u'Image2.jpg': image_path2},
          {'Table_11': [[[u'1'], [u'2'], [u'3']],
                        [[u''], [u'1-2'], [u'3']], 
                        [[u'1'], [u''], [u'2-3']],
                        [[u'', u''], [u'1-2-3']]]}]]
        
        log.debug('sections: {}'.format(returned_sections))
        log.debug('sections: {}'.format(expected_sections))

        self.assertEqual(
            returned_sections,
            expected_sections,
            "Extracted spec sections with tables do not match!")

if __name__ == '__main__':
    unittest.main()
