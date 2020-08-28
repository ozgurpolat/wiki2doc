# pylint: disable=too-many-lines
# -*- coding: utf-8 -*-
"""
Unit tests for wiki2doc.py
"""

import unittest
import sys
import re
from docx import Document
from wiki2doc.wiki2doc import Wiki2Doc

class Wiki2DocTestCase(unittest.TestCase):# pylint: disable=too-many-instance-attributes, too-many-public-methods
    """ Tests for the basic report api """

    def setUp(self):

        filename = 'in.docx'
        filename_adc = 'in_adc.docx'
        filename_sar = 'in_sar.docx'

        document = Document()

    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOOD')
        
if __name__ == '__main__':
    unittest.main()
