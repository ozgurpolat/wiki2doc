from unittest import TestSuite, makeSuite

def test_suite():
    suite = TestSuite()
    from autorep.tests import api, report
    suite.addTest(makeSuite(api.AutoRepApiTestCase))
#    suite.addTest(makeSuite(api.AutoRepPermissionPolicyTestCase))
    suite.addTest(makeSuite(report.ReportTestCase))
    return suite
