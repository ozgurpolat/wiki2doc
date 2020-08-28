# pylint: disable=too-many-lines
"""
Unit tests
"""

import unittest
from wiki2doc.wiki2doc import Wiki2Doc

from trac.test import EnvironmentStub, MockRequest

class Wiki2DocApiTestCase(unittest.TestCase): # pylint: disable=too-many-public-methods
    """ Tests for the basic autorep api """

    def setUp(self):
        self.tktids = None
        self.gr_api = Wiki2Doc(EnvironmentStub()) # pylint: disable=too-many-function-args
    
    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOOD')

if __name__ == '__main__':
    unittest.main()
