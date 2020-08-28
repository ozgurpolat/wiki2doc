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

class Wiki2DocApiTestCase(unittest.TestCase): # pylint: disable=too-many-public-methods
    """ Tests for the basic wiki2doc api """

    def setUp(self):
        self.tktids = None
        self.gr_api = Wiki2Doc(EnvironmentStub()) # pylint: disable=too-many-function-args
    
    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')

    def test_process_request(self):
        """ Test process_request method """

        # test template data for initial view
        req = MockRequest(self.gr_api.env, method='POST',
                          args={'create_report': 'proj3',
                                'form_token': 'bar OGR2',
                                'get_wiki_link': 'http://127.0.0.1:8000/wiki/helloworld'})
        
        template, data, _ = Wiki2Doc.process_request(self.gr_api, req) # pylint: disable=unpacking-non-sequence
        self.assertEqual(template, "wiki2doc.html", "template")

        expected_data = {'tasks': set([(u'Milestone',
                                        u'Task ID, Task Name, Task Type')]),
                         'igrtasks': set([(u'Milestone',
                                           u'Task ID, Task Name, Task Type')]),
                         'form': {'project': u'proj1',
                                  'igrmilestone': u'foo OGR1',
                                  'igrtask': u'None',
                                  'task': u'None',
                                  'milestone': u'foo OGR1'},
                         'igrmilestones': [(u'proj1', u'foo IGR'),
                                           (u'proj2', u'bar IGR')],
                         'milestones': [(u'proj1', u'foo OGR1'),
                                        (u'proj1', u'foo OGR2'),
                                        (u'proj2', u'bar OGR2')],
                         'events': None,
                         'projects': [u'proj1', u'proj2']}

        log.debug('{}'.format(data))

        self.assertEqual(data,
                         expected_data,
                         "Dictionary data returned by " +\
                         "process_request does not match")

        # test redirect
        req = MockRequest(self.gr_api.envs['task'], method='POST',
                          args={'project': 'proj3',
                                'milestone': 'baz OGR2',
                                'task': 'task',
                                'create_report': 'create_report'})

        with patch('trac.web.api.Request.redirect') as mock_redirect:
            try:
                _, data, _ = AutoRep.process_request(self.gr_api, req) # pylint: disable=unpacking-non-sequence
                mock_redirect.assert_called_once_with(
                    '/trac.cgi/autorep?project=proj3&' +\
                    'milestone=baz OGR2&task=task&create_report=create_report')
            except RequestDone:
                self.assertEqual(data, {
                    'tasks': [(u'bar OGR2', u'Task ID, Task Name, Task Type')],
                    'milestones': [(u'proj1', u'foo OGR1'),
                                   (u'proj1', u'foo OGR2'),
                                   (u'proj2', u'bar OGR2')],
                    'form': {'project': 'proj1', 'milestone': 'foo OGR1'},
                    'events': None, 'projects': ['proj1', 'proj2']}, "data")
            except TypeError:
                pass

if __name__ == '__main__':
    unittest.main()
