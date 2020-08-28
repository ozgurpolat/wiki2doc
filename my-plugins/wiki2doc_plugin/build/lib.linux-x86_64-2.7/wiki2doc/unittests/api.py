# pylint: disable=too-many-lines
"""
Tests for as much of autorep as we can
"""

import tempfile
import unittest

from datetime import datetime, timedelta
from docx import Document
from autorep.autorep import AutoRep
from autorep.helpers import\
get_self_referencing_tasks,\
get_preceding_taskids, get_pre_ids_types_tasks,\
get_sections_with_tables,\
filter_wiki_text, filter_regex,\
find_hyperlinks, filter_multi_regex,\
get_storage_of_data, set_keys,\
set_list_of_milestones, request_redirect,\
set_sel_apo_tasks, set_ttype, set_tasks,\
get_sel_apo_task_ids, remove_forward_slash,\
check_for_relative_link, FILTER_STYLES

from simplemultiproject.environmentSetup\
import smpEnvironmentSetupParticipant

from mock import patch
from simplemultiproject.model import SmpModel
from simplemultiproject.smp_model import SmpMilestone
from StringIO import StringIO
from trac.attachment import Attachment
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.model import Ticket
from trac.util.datefmt import utc
from trac.web.api import RequestDone
from trac.wiki import WikiPage
from trac.util.text import to_unicode

def revert_schema(env):
    """ when we've finished, we have to manually
    revert the schema back to vanilla trac """
    with env.db_transaction as dbt:
        for table in ('smp_project', 'smp_milestone_project',
                      'smp_version_project', 'smp_component_project'):
            dbt("DROP TABLE IF EXISTS %s" % dbt.quote(table))
        dbt("DELETE FROM system WHERE name='simplemultiproject_version'")

def _insert_wiki_pages(env, pages):
    """ insert wiki pages """
    time = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
    for name, text in pages.iteritems():
        page = WikiPage(env)
        page.name = name
        page.text = text
        page.save('author', 'comment', '::1', time)

def _modify_ticket(env, tktid, author, when, **kwargs):
    """ modify ticket """
    tkt = Ticket(env, tktid)
    for key, value in kwargs.iteritems():
        tkt[key] = value

    tkt.save_changes(author=author, when=when)

class AutoRepApiTestCase(unittest.TestCase): # pylint: disable=too-many-public-methods
    """ Tests for the basic autorep api """

    n_tickets = 10

    def setUp(self):
        self.tktids = None
        self.gr_api = AutoRep(EnvironmentStub()) # pylint: disable=too-many-function-args

        for instance in self.gr_api.instances:
            self.gr_api.envs[instance] = EnvironmentStub(
                default_data=True,
                enable=["trac.*",
                        "simplemultiproject.*",
                        "mastertickets.*"])

            with self.gr_api.envs[instance].db_transaction as dbt:
                revert_schema(self.gr_api.envs[instance])
                smpEnvironmentSetupParticipant(
                    self.gr_api.envs[instance]).upgrade_environment(dbt)

            model = SmpModel(self.gr_api.envs[instance]) # pylint: disable=too-many-function-args

            model.insert_project("proj1", None, None, None, None)
            model.insert_project("proj2", None, None, None, None)
            model.insert_project("proj3", None, None, None, None)
            model = SmpMilestone(self.gr_api.envs[instance])
            model.add("foo OGR1", 1)
            model.add("bar OGR2", 2)
            model.add("baz", 3)
            model.add("foo OGR2", 1)
            model.add("foo IGR", 1)
            model.add("bar IGR", 2)
            with self.gr_api.envs[instance].db_transaction as dbt:
                dbt("""CREATE TABLE IF NOT EXISTS ticket_custom (
ticket integer, name text, value text, UNIQUE (ticket,name))""")
                dbt("""CREATE TABLE IF NOT EXISTS mastertickets (
source integer, dest integer)""")
        self.gr_api.envs['req'].config.set('ticket-custom', 'link', 'text')
        self.gr_api.envs['req'].config.save()

    def tearDown(self):
        for instance in self.gr_api.instances:
            if hasattr(self.gr_api.envs[instance], 'destroy_db'):
                self.gr_api.envs[instance].destroy_db()
        if hasattr(self.gr_api.env, 'destroy_db'):# pylint: disable=no-member
            self.gr_api.env.destroy_db()# pylint: disable=no-member
        del self.gr_api.env# pylint: disable=no-member
        self.gr_api.errorlog = []

    def _insert_tickets(self, env, **kwargs):
        """ insert tickets """
        when = datetime(2008, 7, 1, 12, 34, 56, 987654, utc)
        with env.db_transaction:
            ids = []
            for idx in xrange(self.n_tickets):
                tkt = Ticket(env)
                tkt['summary'] = 'Summary %d' % idx
                for key, value in kwargs.iteritems():
                    tkt[key] = value[idx % len(value)]
                ids.append(tkt.insert(when=when + timedelta(days=idx)))
                tkt.save_changes('author',
                                 comment='...',
                                 when=when + timedelta(days=idx + 1))
        return ids

    def test_milestones(self):
        """ Tests for the projects and milestones getter """

        model = SmpModel(self.gr_api.envs['task']) # pylint: disable=too-many-function-args
        self.assertEqual(model.get_all_projects(), [
            (1, "proj1", None, None, None, None),
            (2, "proj2", None, None, None, None),
            (3, "proj3", None, None, None, None)], 'list of projects with info')
        model = SmpMilestone(self.gr_api.envs['task'])
        self.assertEqual(6, len(model.get_all_milestones_and_id_project_id()))

        all_projects = self.gr_api.get_all_projects()
        self.assertEqual(all_projects,
                         ["proj1", "proj2", "proj3"],
                         'list of projects')

        milestones = self.gr_api.get_milestones_for_projects(all_projects,
                                                             r".*OGR[12]?\b.*")

        self.assertEqual(milestones,
                         [("proj1", "foo OGR1"),
                          ("proj1", "foo OGR2"),
                          ("proj2", "bar OGR2")],
                         'list of projects + milestones')

        milestones_with_unicode = [
            ("proj1", "foo1"), ("proj1", u'\u2013fo2'), ("proj2", u'b\u2013r'),
            ("proj3", u'b\u2013az'), ("proj3", "baz")]

        self.assertEqual(
            self.gr_api.filter_non_ascii_milestones(milestones_with_unicode),
            [('proj1', 'foo1'),
             ('proj1', u'\u2013fo2'),
             ('proj2', u'b\u2013r'),
             ('proj3', u'b\u2013az'),
             ('proj3', 'baz')],
            'filter_non_ascii_milestones')

    def test_set_keys(self):
        """ Test set_keys method """

        self.tktids = self._insert_tickets(
            self.gr_api.envs['req'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned', 'reopened',
                    'reviewing', 'closed'])

        # test template data for initial view
        req = MockRequest(self.gr_api.envs['task'])
        keys = set_keys(req) # pylint: disable=unpacking-non-sequence

        exp_keys = [None, None, None, None, None, None]

        self.assertEqual(keys,
                         exp_keys,
                         "Request keys do not match!")

        # test redirect
        req = MockRequest(self.gr_api.envs['task'], method='POST',
                          args={'project': 'proj3',
                                'milestone': 'baz OGR2',
                                'task': 'task',
                                'create_report': 'create_report'})

        keys = set_keys(req) # pylint: disable=unpacking-non-sequence

        exp_keys = ['proj3',
                    None,
                    'baz OGR2',
                    None,
                    'task',
                    'Go']

        self.assertEqual(keys,
                         exp_keys,
                         "Request keys do not match!")

    def test_set_ttype(self):# pylint: disable=too-many-locals
        """ Test set_ttype and set_tasks methods """

        model = SmpModel(self.gr_api.envs['task']) # pylint: disable=too-many-function-args
        self.assertEqual(model.get_all_projects(), [
            (1, "proj1", None, None, None, None),
            (2, "proj2", None, None, None, None),
            (3, "proj3", None, None, None, None)], 'list of projects with info')
        model = SmpMilestone(self.gr_api.envs['task'])
        self.assertEqual(6, len(model.get_all_milestones_and_id_project_id()))

        all_projects = self.gr_api.get_all_projects()
        self.assertEqual(all_projects,
                         ["proj1", "proj2", "proj3"],
                         'list of projects')

        milestones = self.gr_api.get_milestones_for_projects(all_projects,
                                                             r".*OGR[12]?\b.*")
        milestones = self.gr_api.filter_non_ascii_milestones(milestones)
        _, set_of_milestones = set_list_of_milestones(milestones)

        igrmilestones = self.gr_api.get_milestones_for_projects(all_projects,
                                                                r".*IGR?\b.*")
        igrmilestones = self.gr_api.filter_non_ascii_milestones(igrmilestones)
        _, set_of_igrmilestones = set_list_of_milestones(igrmilestones)

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar IGR', 'bar OGR2'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 2,
                       'alice', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 3,
                       'bob', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 5,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 8,
                       'bob', when, type='Create Structural Analysis Report',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 9,
                       'bob', when, type='Create Analysis Data Compilation',
                       status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        milestone = 'bar OGR2'

        tasks = set()
        for name in set_of_milestones:
            if name == milestone:
                taskset = set()
                lst_igrtasks = \
                    self.gr_api.get_tasks_for_milestone(
                        to_unicode(milestone))
                for task in lst_igrtasks:
                    taskset.add(task)
                tasks = set_ttype(milestone,
                                  taskset,
                                  'Create Analysis Data Compilation',
                                  'Create Structural Analysis Report')
                lst_tasks = set_tasks(tasks)

        exp_task_sets = set([('bar OGR2',
                              u'8, Summary 7,' +\
                              ' Create Structural Analysis Report')])

        self.assertEqual(tasks,
                         exp_task_sets,
                         "Returned task sets do not match!")

        exp_lst_tasks = [('bar OGR2',
                          u'8, Summary 7, Create Structural Analysis Report')]

        self.assertEqual(lst_tasks,
                         exp_lst_tasks,
                         "Returned task lists do not match!")

        milestone = 'bar IGR'

        tasks = set()
        for name in set_of_igrmilestones:
            if name == milestone:
                taskset = set()
                lst_igrtasks = \
                    self.gr_api.get_tasks_for_milestone(
                        to_unicode(milestone))
                for task in lst_igrtasks:
                    taskset.add(task)
                tasks = set_ttype(milestone,
                                  taskset,
                                  'Create APO Specification',
                                  None)
                lst_tasks = set_tasks(tasks)

        exp_task_sets = set([('bar IGR',
                              u'7, Summary 6, None'),
                             ('bar IGR',
                              u'3, Summary 2, Create APO Specification')])

        self.assertEqual(tasks,
                         exp_task_sets,
                         "Returned task sets do not match!")

        exp_lst_tasks = [('bar IGR',
                          u'3, Summary 2, Create APO Specification'),
                         ('bar IGR',
                          u'7, Summary 6, None')]

        self.assertEqual(lst_tasks,
                         exp_lst_tasks,
                         "Returned task lists do not match!")

    def test_get_flt_gr_tasks(self):# pylint: disable=too-many-locals
        """ Test get_flt_gr_tasks method """

        model = SmpModel(self.gr_api.envs['task']) # pylint: disable=too-many-function-args
        self.assertEqual(model.get_all_projects(), [
            (1, "proj1", None, None, None, None),
            (2, "proj2", None, None, None, None),
            (3, "proj3", None, None, None, None)], 'list of projects with info')
        model = SmpMilestone(self.gr_api.envs['task'])
        self.assertEqual(6, len(model.get_all_milestones_and_id_project_id()))

        all_projects = self.gr_api.get_all_projects()
        self.assertEqual(all_projects,
                         ["proj1", "proj2", "proj3"],
                         'list of projects')

        milestones = self.gr_api.get_milestones_for_projects(all_projects,
                                                             r".*OGR[12]?\b.*")
        milestones = self.gr_api.filter_non_ascii_milestones(milestones)
        projects_i, set_of_milestones = \
            set_list_of_milestones(milestones)

        igrmilestones = self.gr_api.get_milestones_for_projects(all_projects,
                                                                r".*IGR?\b.*")
        igrmilestones = self.gr_api.filter_non_ascii_milestones(igrmilestones)
        projects_ii, set_of_igrmilestones = \
            set_list_of_milestones(igrmilestones)

        exp_projects_i = set([u'proj2', u'proj1'])
        exp_projects_ii = set([u'proj2', u'proj1'])
        exp_milestones = [(u'proj1', u'foo OGR1'),
                          (u'proj1', u'foo OGR2'),
                          (u'proj2', u'bar OGR2')]
        exp_igrmilestones = [(u'proj1',
                              u'foo IGR'),
                             (u'proj2', u'bar IGR')]

        self.assertEqual(projects_i,
                         exp_projects_i,
                         "Projects do not match!")

        self.assertEqual(projects_ii,
                         exp_projects_ii,
                         "Projects do not match!")

        self.assertEqual(milestones,
                         exp_milestones,
                         "OGR milestones do not match!")

        self.assertEqual(igrmilestones,
                         exp_igrmilestones,
                         "IGR milestones do not match!")

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar IGR', 'bar OGR2'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 2,
                       'alice', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 3,
                       'bob', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 5,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 8,
                       'bob', when, type='Create Structural Analysis Report',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 9,
                       'bob', when, type='Create Analysis Data Compilation',
                       status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        # test redirect
        req = MockRequest(self.gr_api.envs['task'], method='POST',
                          args={'project': 'proj3',
                                'milestone': 'bar OGR2',
                                'igrmilestone': 'bar IGR',
                                'task': 'task',
                                'create_report': 'create_report'})

        keys = set_keys(req) # pylint: disable=unpacking-non-sequence
        exp_keys = ['proj3', 'bar IGR', 'bar OGR2', None, 'task', 'Go']

        self.assertEqual(keys,
                         exp_keys,
                         "Request keys do not match!")

        igrtasks = self.gr_api.get_flt_gr_tasks(keys[1],
                                                set_of_igrmilestones,
                                                'Create APO Specification',
                                                None)

        exp_igrtasks = [('bar IGR',
                         u'3, Summary 2, Create APO Specification'),
                        ('bar IGR', u'7, Summary 6, None')]

        self.assertEqual(igrtasks,
                         exp_igrtasks,
                         "IGR tasks do not match!")

        ogrtasks = \
            self.gr_api.get_flt_gr_tasks(keys[2],
                                         set_of_milestones,
                                         'Create Analysis Data Compilation',
                                         'Create Structural Analysis Report')

        exp_ogrtasks = [('bar OGR2',
                         u'8, Summary 7, Create Structural Analysis Report')]

        self.assertEqual(ogrtasks,
                         exp_ogrtasks,
                         "OGR tasks do not match!")

    def test_set_default_data(self):# pylint: disable=too-many-locals
        """ Test set_default_data and set_data methods """

        model = SmpModel(self.gr_api.envs['task']) # pylint: disable=too-many-function-args
        self.assertEqual(model.get_all_projects(), [
            (1, "proj1", None, None, None, None),
            (2, "proj2", None, None, None, None),
            (3, "proj3", None, None, None, None)], 'list of projects with info')
        model = SmpMilestone(self.gr_api.envs['task'])
        self.assertEqual(6, len(model.get_all_milestones_and_id_project_id()))

        all_projects = self.gr_api.get_all_projects()
        self.assertEqual(all_projects,
                         ["proj1", "proj2", "proj3"],
                         'list of projects')

        milestones = self.gr_api.get_milestones_for_projects(all_projects,
                                                             r".*OGR[12]?\b.*")
        milestones = self.gr_api.filter_non_ascii_milestones(milestones)
        projects_i, _ = set_list_of_milestones(milestones)

        igrmilestones = self.gr_api.get_milestones_for_projects(all_projects,
                                                                r".*IGR?\b.*")
        igrmilestones = self.gr_api.filter_non_ascii_milestones(igrmilestones)
        projects_ii, _ = set_list_of_milestones(igrmilestones)

        projects = projects_i | projects_ii

        self.gr_api.set_default_data(projects, igrmilestones, milestones)

        data = {'tasks': set([(u'Milestone',
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

        self.assertEqual(self.gr_api.data,
                         data,
                         "self.gr_api.data does not match!")

    def test_set_list_of_milestones(self):# pylint: disable=too-many-locals
        """ Test set_list_of_milestones methods """

        projects = set([u'proj2',
                        u'proj1'])

        milestones = [(u'proj1', u'foo OGR1'),
                      (u'proj1', u'foo OGR1'),
                      (u'proj1', u'foo OGR2'),
                      (u'proj2', u'bar OGR2')]

        projects_i, set_of_milestones = \
            set_list_of_milestones(milestones)

        self.assertEqual(projects,
                         projects_i,
                         "Sets of projects do not match!")

        exp_set_of_milestones = set([u'foo OGR1',
                                     u'foo OGR2',
                                     u'bar OGR2'])

        self.assertEqual(set_of_milestones,
                         exp_set_of_milestones,
                         "Sets of milestones do not match!")

        igrmilestones = [(u'proj1', u'foo IGR'),
                         (u'proj1', u'foo IGR'),
                         (u'proj2', u'bar IGR'),
                         (u'proj2', u'bar IGR')]

        projects_ii, set_of_igrmilestones = \
            set_list_of_milestones(igrmilestones)

        projects = set([u'proj2',
                        u'proj1'])

        self.assertEqual(projects,
                         projects_ii,
                         "Sets of projects do not match!")

        exp_set_of_igrmilestones = set([u'foo IGR',
                                        u'bar IGR'])

        self.assertEqual(set_of_igrmilestones,
                         exp_set_of_igrmilestones,
                         "Sets of igr milestones do not match!")

    def test_request_redirect(self):
        """ Test request_redirect method """

        # test redirect
        req = MockRequest(self.gr_api.envs['task'], method='POST',
                          args={'project': 'proj3',
                                'milestone': 'baz OGR2',
                                'igrtask': 'igrtask',
                                'task': 'task',
                                'create_report': 'create_report'})

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

    def test_set_sel_apo_tasks(self):
        """ Test set_sel_apo_tasks method """

        # test redirect
        req = MockRequest(self.gr_api.envs['task'], method='POST',
                          args={'project': 'proj3',
                                'milestone': 'baz OGR2',
                                'igrtask': 'igrtask',
                                'task': 'task',
                                'chk_1': '11347, Lorem Ipsum,' +\
                                ' Create APO Specification',
                                'chk_2': '11348, Dolor Sit,' +\
                                ' Create APO Specification',
                                'chk_3': '11345, Amet consetetur,' +\
                                ' Create APO Specification',
                                'chk_4': '11346, sadipscing elitr,' +\
                                ' Create APO Specification',
                                'create_report': 'create_report'})

        sel_apo_tasks = set_sel_apo_tasks(req) # pylint: disable=unpacking-non-sequence

        exp_sel_apo_tasks = ['11347, Lorem Ipsum,' +\
                             ' Create APO Specification',
                             '11348, Dolor Sit,' +\
                             ' Create APO Specification',
                             '11346, sadipscing elitr,' +\
                             ' Create APO Specification',
                             '11345, Amet consetetur,' +\
                             ' Create APO Specification']

        self.assertEqual(sel_apo_tasks,
                         exp_sel_apo_tasks,
                         "Selected apo tasks do not match!")

    def test_get_sel_apo_task_ids(self):
        """ Test get_sel_apo_task_ids method """

        sel_apo_tasks = ['11347, Lorem Ipsum, Create APO Specification',
                         '11348, Dolor Sit, Create APO Specification',
                         '11346, sadipscing elitr, Create APO Specification',
                         '11345, Amet consetetur, Create APO Specification']

        exp_sel_apo_task_ids = ['11347',
                                '11348',
                                '11346',
                                '11345']

        self.assertEqual(get_sel_apo_task_ids(sel_apo_tasks),
                         exp_sel_apo_task_ids,
                         "Selected apo task ids do not match!")

    def test_process_request(self):
        """ Test process_request method """

        self.tktids = self._insert_tickets(
            self.gr_api.envs['req'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned', 'reopened',
                    'reviewing', 'closed'])

        # test template data for initial view
        req = MockRequest(self.gr_api.envs['task'])
        template, data, _ = AutoRep.process_request(self.gr_api, req) # pylint: disable=unpacking-non-sequence
        self.assertEqual(template, "autorep.html", "template")

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

    def test_get_tasks_for_milestone(self):
        """ Test get_tasks_for_milestone """

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'alice', when, status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        tasks = self.gr_api.get_tasks_for_milestone('baz')
        self.assertEqual(tasks, [
            (4, 'Summary 3', 'defect', 'reviewing', None, None,
             'someone_else', 'alice', '2008-08-01', None, None,
             None, None, None, None, None, None),
            (8, 'Summary 7', 'enhancement', None,
             None, None, 'someone', None, None,
             None, None, None, None, None, None,
             None, None)], "get_tasks_for_milestone")

        when = datetime(2008, 8, 3, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, status='closed')
        _modify_ticket(self.gr_api.envs['task'], 8,
                       'alice', when, status='reviewing')

        tasks = self.gr_api.get_tasks_for_milestone('baz')
        self.assertEqual(tasks, [
            (4, 'Summary 3', 'defect', 'closed', None, None,
             'someone_else', 'alice', '2008-08-01', 'bob', '2008-08-03', None,
             None, None, None, None, None),
            (8, 'Summary 7', 'enhancement', 'reviewing', None, None,
             'someone', 'alice', '2008-08-03', None, None, None,
             None, None, None, None, None)], "get_tasks_for_milestone2")

    def test_get_template(self):
        """ Test get_template method """

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.envs['req']
        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')

        req = MockRequest(self.gr_api.envs['task'])

        page = 'WikiStart'
        with env.db_transaction as dtb:
            dtb("INSERT INTO wiki (name,version) VALUES ('{}',1)".format(page))
        attachment = Attachment(env, 'wiki', page)
        attachment.insert('AutoReportTemplate_v.docm', StringIO(''), 0)

        template_name = 'AutoReportTemplate_v2.docm'

        path = None

        self.assertEqual(self.gr_api.get_template(template_name, req),
                         path,
                         "Returned attachment path must be None!")

        errorlog = [('Attachment AutoReportTemplate_v2.docm' +\
                     ' could not be found at WikiStart.',
                     0,
                     'http://example.org/Coconut/event/' +\
                     'wiki/WikiStart')]

        self.assertEqual(self.gr_api.errorlog,
                         errorlog,
                         "Errorlog does not match")

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.envs['req']
        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')

        page = 'WikiStart'
        with env.db_transaction as dtb:
            dtb("DELETE FROM wiki")
            dtb("VACUUM")
            dtb("INSERT INTO wiki (name,version) VALUES ('{}',1)".format(page))
        attachment = Attachment(env, 'wiki', page)
        attachment.insert('AutoReportTemplate_v3.docm', StringIO(''), 0)

        template_name = 'AutoReportTemplate_v3.docm'

        errorlog = []

        self.gr_api.get_template(template_name, req)

        self.assertEqual(self.gr_api.errorlog,
                         errorlog,
                         "Errorlog is not empty!")

    #pylint: disable=too-many-locals
    def test_select_report_template(self):# pylint: disable=too-many-statements
        """ Test select_report_template method """

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.envs['req']
        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')

        req = MockRequest(self.gr_api.envs['task'])

        page = 'WikiStart'
        with env.db_transaction as dtb:
            dtb("INSERT INTO wiki (name,version) VALUES ('{}',1)".format(page))
        attachment = Attachment(env, 'wiki', page)
        attachment.insert('AutoReportTemplate_v2.docm', StringIO(''), 0)

        # create empty docx
        document = Document()
        document.save(attachment.path)

        env = self.gr_api.envs['task']
        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 2,
                       'alice', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 3,
                       'bob', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 5,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 8,
                       'bob', when, type='Create Structural Analysis Report',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 9,
                       'bob', when, type='Create Analysis Data Compilation',
                       status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        with env.db_transaction as dtb:
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[0], self.tktids[1]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[5], self.tktids[6]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[7]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[8]))

            text = """= 2. Introduction[=#Ch2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 2.1. Structural Function [=#Ch2.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 2.2. Skill [=#Ch2.2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 3.1 List of Design Solutions [=#Ch3.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
=== 3.1.1 Outstanding DQN [=#Ch3.1.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 3.2 Material Data[=#Ch3.2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 3.3 Fastener Data [=#Ch3.3]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 4.1 Applicable FEMs [=#Ch4.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
= 4. Stress Input [=#Ch4]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 4.2 Applicable Load Cases [=#Ch4.2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 4.3 Sizing Criteria / Failure Modes [=#Ch4.3]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 4.4 Applicable Factors [=#Ch4.4]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
= 5 References [=#Ch5]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 5.1 Documents[=#Ch5.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 5.2 Software[=#Ch5.2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 5.3 Abbreviations and Units[=#Ch5.3]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
= 6 Miscellaneous / Assumptions / Uncertainties / Findings[=#Ch6]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
"""

        with env.db_transaction as dtb:
            dtb("INSERT INTO wiki (name,version,text) " +\
                "VALUES ('{}',1, '{}')".format('name1', text))
            dtb("INSERT INTO wiki (name,version,text) " +\
                "VALUES ('{}',1, '{}')".format('name2', text))
            dtb("INSERT INTO wiki (name,version,text) " +\
                "VALUES ('{}',1, '{}')".format('name3', text))

        with env.db_transaction as dtb:
            dtb("INSERT INTO ticket_custom (ticket,name,value) " +\
                "VALUES ('{}','{}','{}')"\
                .format(2,
                        'spec_link',
                        '[http://localhost/Coconut/event/wiki/name1 name1]'))
            dtb("INSERT INTO ticket_custom (ticket,name,value) " +\
                "VALUES ('{}','{}','{}')"\
                .format(3,
                        'spec_link',
                        '[http://localhost/Coconut/event/wiki/name2 name2]'))
            dtb("INSERT INTO ticket_custom (ticket,name,value) " +\
                "VALUES ('{}','{}','{}')"\
                .format(4,
                        'spec_link',
                        '[http://localhost/Coconut/event/wiki/name3 name3]'))

        task = "8, " +\
            "Lorem Ipsum Dolor Sit Amet, " +\
            "Create Structural Analysis Report"

        sel_apo_task_ids = [3]

        report, report_ttype,\
        create_apo_specs, analyse_apo_tasks =\
            self.gr_api.select_report_template(task,
                                               sel_apo_task_ids,
                                               req)

        exp_report_type = 'SAR'

        exp_report_ttype = 'Create Structural Analysis Report'

        exp_create_apo_specs = [[3,
                                 u'name2',
                                 u'= 2. Introduction[=#Ch2]\n' +\
                                 'Lorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '== 2.1. Structural Function [=#Ch2.1]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 2.2. Skill' +\
                                 ' [=#Ch2.2]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '== 3.1 List of Design Solutions' +\
                                 ' [=#Ch3.1]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '=== 3.1.1 Outstanding DQN [=#Ch3.1.1]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 3.2 Material' +\
                                 ' Data[=#Ch3.2]\nLorem ipsum dolor sit' +\
                                 ' amet, consetetur sadipscing elitr.\n' +\
                                 '== 3.3 Fastener Data [=#Ch3.3]\nLorem' +\
                                 ' ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 4.1 Applicable' +\
                                 ' FEMs [=#Ch4.1]\nLorem ipsum dolor' +\
                                 ' sit amet, consetetur sadipscing' +\
                                 ' elitr.\n= 4. Stress Input [=#Ch4]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 4.2 Applicable' +\
                                 ' Load Cases [=#Ch4.2]\nLorem ipsum' +\
                                 ' dolor sit amet, consetetur sadipscing' +\
                                 ' elitr.\n== 4.3 Sizing Criteria /' +\
                                 ' Failure Modes [=#Ch4.3]\nLorem ipsum' +\
                                 ' dolor sit amet, consetetur sadipscing' +\
                                 ' elitr.\n== 4.4 Applicable Factors' +\
                                 ' [=#Ch4.4]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '= 5 References [=#Ch5]\nLorem ipsum' +\
                                 ' dolor sit amet, consetetur sadipscing' +\
                                 ' elitr.\n== 5.1 Documents[=#Ch5.1]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 5.2 Software' +\
                                 '[=#Ch5.2]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '== 5.3 Abbreviations and Units[=#Ch5.3]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n= 6 Miscellaneous /' +\
                                 ' Assumptions / Uncertainties /' +\
                                 ' Findings[=#Ch6]\nLorem ipsum dolor' +\
                                 ' sit amet, consetetur sadipscing elitr.\n']]

        exp_analyse_apo_tasks = None

        exp_errorlog = []

        self.assertEqual(
            report.report_type,
            exp_report_type,
            "Returned report type does not match!")

        self.assertEqual(
            report_ttype,
            exp_report_ttype,
            "Returned report task type does not match!")

        self.assertEqual(
            create_apo_specs,
            exp_create_apo_specs,
            "Returned list of create_apo_specs does not match!")

        self.assertEqual(
            analyse_apo_tasks,
            exp_analyse_apo_tasks,
            "Returned list of analyse_apo_tasks does not match!")

        self.assertEqual(
            self.gr_api.errorlog,
            exp_errorlog,
            "Errorlogs do not match!")

        self.gr_api.errorlog = []

        task = "9, " +\
            "Lorem Ipsum Dolor Sit Amet, " +\
            "Create Analysis Data Compilation"

        sel_apo_task_ids = [3]

        report, report_ttype,\
        create_apo_specs, analyse_apo_tasks =\
            self.gr_api.select_report_template(task,
                                               sel_apo_task_ids,
                                               req)

        exp_report_type = 'ADC'

        exp_report_ttype = 'Create Analysis Data Compilation'

        exp_create_apo_specs = [[3,
                                 u'name2',
                                 u'= 2. Introduction[=#Ch2]\n' +\
                                 'Lorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '== 2.1. Structural Function [=#Ch2.1]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 2.2. Skill' +\
                                 ' [=#Ch2.2]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '== 3.1 List of Design Solutions' +\
                                 ' [=#Ch3.1]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '=== 3.1.1 Outstanding DQN [=#Ch3.1.1]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 3.2 Material' +\
                                 ' Data[=#Ch3.2]\nLorem ipsum dolor sit' +\
                                 ' amet, consetetur sadipscing elitr.\n' +\
                                 '== 3.3 Fastener Data [=#Ch3.3]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 4.1 Applicable' +\
                                 ' FEMs [=#Ch4.1]\nLorem ipsum dolor' +\
                                 ' sit amet, consetetur sadipscing elitr.\n' +\
                                 '= 4. Stress Input [=#Ch4]\nLorem ipsum' +\
                                 ' dolor sit amet, consetetur sadipscing' +\
                                 ' elitr.\n== 4.2 Applicable Load Cases' +\
                                 ' [=#Ch4.2]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '== 4.3 Sizing Criteria / Failure Modes' +\
                                 ' [=#Ch4.3]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '== 4.4 Applicable Factors [=#Ch4.4]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n= 5 References' +\
                                 ' [=#Ch5]\nLorem ipsum dolor sit amet,' +\
                                 ' consetetur sadipscing elitr.\n' +\
                                 '== 5.1 Documents[=#Ch5.1]\nLorem ipsum' +\
                                 ' dolor sit amet, consetetur sadipscing' +\
                                 ' elitr.\n== 5.2 Software[=#Ch5.2]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n== 5.3 Abbreviations' +\
                                 ' and Units[=#Ch5.3]\nLorem ipsum dolor' +\
                                 ' sit amet, consetetur sadipscing elitr.\n' +\
                                 '= 6 Miscellaneous / Assumptions /' +\
                                 ' Uncertainties / Findings[=#Ch6]\n' +\
                                 'Lorem ipsum dolor sit amet, consetetur' +\
                                 ' sadipscing elitr.\n']]

        exp_analyse_apo_tasks = None

        exp_errorlog = [('Check the linking of the tasks.' +\
                         ' Preceeding Analyse APO' +\
                         ' task list is empty for task: 9!',
                         'http://example.org/Coconut/task/ticket/9',
                         'None'),
                        ('Associated Analyse APO tasks' +\
                         ' could not be found for Task ID 9.',
                         'http://example.org/Coconut/' +\
                         'task/ticket/9',
                         'None'),
                        ('Attachment AutoAdcTemplate_v3.docm' +\
                         ' could not be found at WikiStart.',
                         0,
                         'http://example.org/Coconut/' +\
                         'event/wiki/WikiStart')]

        self.assertEqual(
            report.report_type,
            exp_report_type,
            "Returned report type does not match!")

        self.assertEqual(
            report_ttype,
            exp_report_ttype,
            "Returned report task type does not match!")

        self.assertEqual(
            create_apo_specs,
            exp_create_apo_specs,
            "Returned list of create_apo_specs does not match!")

        self.assertEqual(
            analyse_apo_tasks,
            exp_analyse_apo_tasks,
            "Returned list of analyse_apo_tasks does not match!")

        self.assertEqual(
            self.gr_api.errorlog,
            exp_errorlog,
            "Errorlogs do not match!")

        self.gr_api.errorlog = []

        task = "8, " +\
            "Lorem Ipsum Dolor Sit Amet, " +\
            "Create Structural Analysis Report"

        sel_apo_task_ids = [11]

        report, report_ttype,\
        create_apo_specs, analyse_apo_tasks =\
            self.gr_api.select_report_template(task,
                                               sel_apo_task_ids,
                                               req)

        exp_errorlog = [('Associated Create APO tasks' +\
                         ' could not be found for Task ID 8.',
                         'http://example.org/Coconut/' +\
                         'task/ticket/8',
                         'None')]

        self.assertEqual(
            self.gr_api.errorlog,
            exp_errorlog,
            "Errorlogs do not match!")

    def test_process_report_task(self):# pylint: disable=too-many-statements
        """ Test the process_report_task method """

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.envs['req']
        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')

        req = MockRequest(self.gr_api.envs['task'])

        page = 'WikiStart'
        with env.db_transaction as dtb:
            dtb("INSERT INTO wiki (name,version) VALUES ('{}',1)".format(page))
        attachment = Attachment(env, 'wiki', page)
        attachment.insert('AutoReportTemplate_v2.docm', StringIO(''), 0)

        # create empty docx
        document = Document()
        document.save(attachment.path)

        env = self.gr_api.envs['task']
        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 2,
                       'alice', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 3,
                       'bob', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, type='Create APO Specification',
                       status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 5,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 8,
                       'bob', when, type='Create Structural Analysis Report',
                       status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        with env.db_transaction as dtb:
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[0], self.tktids[1]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[5], self.tktids[6]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[7]))

            text = """= 2. Introduction[=#Ch2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 2.1. Structural Function [=#Ch2.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 2.2. Skill [=#Ch2.2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 3.1 List of Design Solutions [=#Ch3.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
=== 3.1.1 Outstanding DQN [=#Ch3.1.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 3.2 Material Data[=#Ch3.2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 3.3 Fastener Data [=#Ch3.3]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 4.1 Applicable FEMs [=#Ch4.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
= 4. Stress Input [=#Ch4]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 4.2 Applicable Load Cases [=#Ch4.2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 4.3 Sizing Criteria / Failure Modes [=#Ch4.3]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 4.4 Applicable Factors [=#Ch4.4]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
= 5 References [=#Ch5]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 5.1 Documents[=#Ch5.1]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 5.2 Software[=#Ch5.2]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
== 5.3 Abbreviations and Units[=#Ch5.3]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
= 6 Miscellaneous / Assumptions / Uncertainties / Findings[=#Ch6]
Lorem ipsum dolor sit amet, consetetur sadipscing elitr.
"""

        with env.db_transaction as dtb:
            dtb("INSERT INTO wiki (name,version,text) " +\
                "VALUES ('{}',1, '{}')".format('name1', text))
            dtb("INSERT INTO wiki (name,version,text) " +\
                "VALUES ('{}',1, '{}')".format('name2', text))
            dtb("INSERT INTO wiki (name,version,text) " +\
                "VALUES ('{}',1, '{}')".format('name3', text))

        with env.db_transaction as dtb:
            dtb("INSERT INTO ticket_custom (ticket,name,value) " +\
                "VALUES ('{}','{}','{}')"\
                .format(2,
                        'spec_link',
                        '[http://localhost/Coconut/event/wiki/name1 name1]'))
            dtb("INSERT INTO ticket_custom (ticket,name,value) " +\
                "VALUES ('{}','{}','{}')"\
                .format(3,
                        'spec_link',
                        '[http://localhost/Coconut/event/wiki/name2 name2]'))
            dtb("INSERT INTO ticket_custom (ticket,name,value) " +\
                "VALUES ('{}','{}','{}')"\
                .format(4,
                        'spec_link',
                        '[http://localhost/Coconut/event/wiki/name3 name3]'))

        task = "8, " +\
            "Lorem Ipsum Dolor Sit Amet, " +\
            "Create Structural Analysis Report"

        sel_apo_tasks = [u'2, name1, Create APO Specification',
                         u'3, name2, Create APO Specification',
                         u'4, name3, Create APO Specification']

        parameters = [sel_apo_tasks,
                      task,
                      req]

        errorlog, content = self.gr_api.process_report_task(parameters)

        exp_errorlog = []

        self.assertEqual(len(content), 36718, "returned content for task 8")
        self.assertEqual(errorlog, exp_errorlog, "Errorlog is not empty")

        self.gr_api.errorlog = []

        task = "8, " +\
            "Lorem Ipsum Dolor Sit Amet, " +\
            "Create Structural Analysis Report"

        sel_apo_tasks = [u'11, name1, Create APO Specification']

        parameters = [sel_apo_tasks,
                      task,
                      req]

        errorlog, content = self.gr_api.process_report_task(parameters)

        exp_errorlog = [('Associated Create APO tasks' +\
                         ' could not be found for Task ID 8.',
                         'http://example.org/Coconut/task/ticket/8',
                         'None'),
                        (u'Create APO spec list is empty.' +\
                         ' Check to see if the apo spec' +\
                         ' is linked properly in following' +\
                         ' create apo task! or tasks:' +\
                         '\n\nTask ID = 11\n',
                         u'11',
                         'None')]

        self.assertEqual(len(content), 36469, "returned content for task 8")
        self.assertEqual(errorlog, exp_errorlog, "Errorlog does not not match")

        #pylint: disable=too-many-function-args
        with self.assertRaises(TypeError):
            self.gr_api.process_report_task(parameters,
                                            'test')

        with self.assertRaises(TypeError):
            self.gr_api.process_report_task(parameters,
                                            'test')#pylint: disable=too-many-function-args

    def test_get_taskid_pairs_from_db(self):
        """ Test get_taskid_pairs_from_db """

        env = self.gr_api.envs['task']

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '',
                    'new',
                    'assigned',
                    'reopened',
                    'reviewing',
                    'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'alice', when, status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        with env.db_transaction as dtb:
            for idx in range(len(self.tktids)):
                if idx+1 < len(self.tktids):
                    dtb("INSERT INTO mastertickets " +\
                        "(source,dest) VALUES ('{}','{}')"\
                        .format(self.tktids[idx], self.tktids[idx+1]))
                if idx+1 == len(self.tktids):
                    dtb("INSERT INTO mastertickets " +\
                        "(source,dest) VALUES ('{}','{}')"\
                        .format(self.tktids[idx], self.tktids[0]))

        taskid_pairs = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6),
                        (6, 7), (7, 8), (8, 9), (9, 10), (10, 1)]
        self.assertEqual(
            self.gr_api.get_taskid_pairs_from_db(),
            taskid_pairs,
            "Task ID pairs do not match!")

    def test_get_self_referencing_tasks(self):
        """ Test get_self_referencing_tasks """

        taskid_pairs = [(3, 6), (4, 6), (5, 6)]
        filtered_taskid_pairs = []

        self.assertEqual(
            get_self_referencing_tasks(taskid_pairs),
            filtered_taskid_pairs,
            "Self referencing taskid pairs for empty list do not match!")

        taskid_pairs = [(1, 2), (2, 2), (3, 4), (4, 5), (5, 6),
                        (6, 7), (7, 8), (8, 9), (9, 9), (10, 1)]
        filtered_taskid_pairs = [2, 9]

        self.assertEqual(
            get_self_referencing_tasks(taskid_pairs),
            filtered_taskid_pairs,
            "Returned self referencing taskid pairs do not match!")


    def test_get_preceding_taskids(self):
        """ Test get_preceding_taskids """

        taskid = 6
        taskid_pairs = [(3, 6), (4, 6), (5, 6)]

        preceding_taskids = [3, 4, 5]

        self.assertEqual(
            get_preceding_taskids(taskid, taskid_pairs),
            preceding_taskids,
            "Returned preceding task ids do not match!")

    def test_get_task_info(self):
        """ Test get_task_info """

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'alice', when, status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        task_info = [(1, u'Summary 0', None, u'closed', None,
                      None, None, u'bob', u'2008-08-01', u'bob',
                      u'2008-08-02', None, None, None, None,
                      None, None, None, None, None),
                     (2, u'Summary 1', None, None, None,
                      None, None, None, None, None,
                      None, None, None, None, None,
                      None, None, None, None, None)]

        self.assertEqual(
            self.gr_api.get_task_info([1, 2]),
            task_info,
            "Returned task_infos do not match!")

    def test_get_pre_ids_types_tasks(self):
        """ Test get_pre_ids_types_tasks """

        env = self.gr_api.envs['task']

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'alice', when, status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        with env.db_transaction as dtb:
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[4], self.tktids[5]))

        tasks = [
            (3, u'Summary 2', u'enhancement', u'new', None, None,
             u'someone', None, None, None, None, None,
             None, None, None, None, None, u'bar'),
            (4, u'Summary 3', u'defect', u'reviewing', None, None,
             u'someone_else', None, None, None, None, None,
             None, None, None, None, None, u'baz'),
            (5, u'Summary 4', u'task', u'reopened', None, None,
             u'none', None, None, None, None, None,
             None, None, None, None, None, None)
        ]

        ids_types_tasks = [
            (3, u'enhancement',
             (3, u'Summary 2', u'enhancement', u'new', None, None,
              u'someone', None, None, None, None, None,
              None, None, None, None, None, u'bar')),
            (4, u'defect',
             (4, u'Summary 3', u'defect', u'reviewing', None, None,
              u'someone_else', None, None, None, None, None,
              None, None, None, None, None, u'baz')),
            (5, u'task',
             (5, u'Summary 4', u'task', u'reopened', None, None,
              u'none', None, None, None, None, None,
              None, None, None, None, None, None))]

        self.assertEqual(
            get_pre_ids_types_tasks(tasks),
            ids_types_tasks,
            "Returned task id, task type and task do not match!")

#pylint: disable=too-many-statements
    def test_get_tasks_for_ttype(self):
        """ Test get_tasks_for_ttype """

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.envs['task']

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 2,
                       'alice', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 3,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 5,
                       'bob', when, type='easy', status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        with env.db_transaction as dtb:
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[4], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[5], self.tktids[6]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[7]))

        easy_tasks = [(2, u'Summary 1', u'easy', u'reviewing', None,
                       None, None, None, None, None,
                       None, None, None, None, None,
                       None, None, None, None, None),
                      (3, u'Summary 2', u'easy', u'reviewing', None,
                       None, u'someone', None, None, None,
                       None, None, None, None, None,
                       None, None, u'bar', None, None),
                      (4, u'Summary 3', u'easy', u'reviewing', None,
                       None, u'someone_else', None, None, None,
                       None, None, None, None, None,
                       None, None, u'baz', None, None),
                      (5, u'Summary 4', u'easy', u'reviewing', None,
                       None, u'none', u'bob', u'2008-08-01', None,
                       None, None, None, None, None,
                       None, None, None, None, None)]

        req = MockRequest(self.gr_api.envs['task'])

        report_taskid = 8
        ttype = "easy"
        taskid_pairs = [(2, 6), (3, 6), (4, 6), (5, 6), (6, 7), (7, 8)]
        self_ref_taskids = []

        params = [None,
                  taskid_pairs,
                  self_ref_taskids,
                  report_taskid,
                  req]

        get_easy_tasks = self.gr_api.get_tasks_for_ttype(params,
                                                         ttype)

        self.assertEqual(get_easy_tasks, easy_tasks,
                         "Selected tasks do not match!")

        with env.db_transaction as dtb:
            dtb("DELETE FROM mastertickets")
            dtb("VACUUM")
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[1]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[2]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[4], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[5], self.tktids[6]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[7]))

        self.gr_api.errorlog = []
        report_taskid = 8
        ttype = "easy"
        taskid_pairs = [(2, 2), (3, 3), (2, 6), (3, 6),
                        (4, 6), (5, 6), (6, 7), (7, 8)]
        self_ref_taskids = [2, 3]

        params = [None,
                  taskid_pairs,
                  self_ref_taskids,
                  report_taskid,
                  req]

        self.gr_api.get_tasks_for_ttype(
            params,
            ttype)

        errorlog = [('Self-referencing task/s found. Remove the' +\
                     ' self reference from the task/s and correct' +\
                     ' the preceding and/or successor task-id/s' +\
                     ' for Task: 2',
                     'http://example.org/Coconut/task/ticket/2',
                     'None'),
                    ('Self-referencing task/s found. Remove the' +\
                     ' self reference from the task/s and' +\
                     ' correct the preceding and/or successor' +\
                     ' task-id/s for Task: 3',
                     'http://example.org/Coconut/task/ticket/3',
                     'None')]

        self.assertEqual(self.gr_api.errorlog, errorlog,
                         "Errorlogs for self-referencing tasks "+\
                         "do not match!")

        with env.db_transaction as dtb:
            dtb("DELETE FROM mastertickets")
            dtb("VACUUM")
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[4], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[5], self.tktids[6]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[7]))

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        report_taskid = 8
        ttype = "easy"
        taskid_pairs = [(2, 6), (3, 6), (4, 6), (5, 6), (7, 8)]
        self_ref_taskids = []

        params = [None,
                  taskid_pairs,
                  self_ref_taskids,
                  report_taskid,
                  req]

        self.gr_api.get_tasks_for_ttype(
            params,
            ttype)

        errorlog = [('Check the linking of the tasks. ' +\
                     'Preceeding easy task list is ' +\
                     'empty for task: 8!',
                     'http://example.org/Coconut/task/ticket/8',
                     'None')]

        self.assertEqual(self.gr_api.errorlog, errorlog,
                         "Errorlogs for empty preceding task list "+\
                         "do not match!")

    def test_match_spec_path(self):
        """ Test match_spec_path """

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.envs['task']

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 2,
                       'alice', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 3,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 5,
                       'bob', when, type='easy', status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        with env.db_transaction as dtb:
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[4], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[5], self.tktids[6]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[7]))

        easy_tasks = [
            (5, u'Summary 4', u'easy', u'reviewing', None, None,
             u'none', u'bob', u'2008-08-01', None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname4|Specname4]]',
             None, None, None, None, None)]

        page_path = 'http://localhost/Coconut/event/wiki/Specname4'

        req = MockRequest(self.gr_api.envs['task'])

        self.assertEqual(
            self.gr_api.match_spec_path(easy_tasks[0], req),
            page_path,
            "Page path does not match!")

        easy_tasks = [
            (5, u'Summary 4', u'easy', u'reviewing', None, None,
             u'none', u'bob', u'2008-08-01', None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname4||Specname4]]',
             None, None, None, None, None)]

        self.gr_api.match_spec_path(easy_tasks[0], req)

        errorlog = [('Please check the number of pipe symbols (|)' +\
                     ' or spaces in the link to APO specification' +\
                     ' in Task ID = 5\n',
                     'http://example.org/Coconut/task/ticket/5',
                     'None')]

        self.assertEqual(
            self.gr_api.errorlog,
            errorlog,
            "Errorlogs do not match!")

    def test_get_specs_id_name_text(self):
        """ Test get_specs_id_name_text """

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.envs['task']

        req = MockRequest(self.gr_api.envs['task'])

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 2,
                       'alice', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 3,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 5,
                       'bob', when, type='easy', status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        with env.db_transaction as dtb:
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[4], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[5], self.tktids[6]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[7]))

        easy_tasks = [
            (2, u'Summary 1', u'easy', u'reviewing', None, None,
             None, None, None, None, None, None,
             '[http://localhost/Coconut/event/wiki/Specname1 Link1]',
             None, None, None, None, None),
            (3, u'Summary 2', u'easy', u'reviewing', None, None,
             u'someone', None, None, None, None, None,
             '[http://localhost/Coconut/event/wiki/Specname2]',
             None, None, None, None, u'bar'),
            (4, u'Summary 3', u'easy', u'reviewing', None, None,
             u'someone_else', None, None, None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname3|Link3]]',
             None, None, None, None, u'baz'),
            (5, u'Summary 4', u'easy', u'reviewing', None, None,
             u'none', u'bob', u'2008-08-01', None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname4]]',
             None, None, None, None, None),
            (2, u'Summary 1', u'easy', u'reviewing', None, None,
             None, None, None, None, None, None,
             '[[e:/wiki/Specname1]]',
             None, None, None, None, None),
            (3, u'Summary 2', u'easy', u'reviewing', None, None,
             u'someone', None, None, None, None, None,
             '[[e:/wiki/Specname2|Specname2]]',
             None, None, None, None, u'bar')]

        pages = {
            'Specname1': """Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
invidunt ut labore et dolore magna aliquyam erat, sed diam
voluptua.""",
            'Specname2': """At vero eos et accusam et justo duo dolores et
ea rebum. Stet clita kasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet.""",
            'Specname3': """Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
invidunt ut labore et dolore magna aliquyam erat, sed diam
voluptua.""",
            'Specname4': """At vero eos et accusam et justo duo dolores et
ea rebum. Stet clita kasd gubergren, no sea takimata
sanctus est Lorem ipsum dolor sit amet."""}
        _insert_wiki_pages(self.gr_api.envs['event'], pages)

        path = 'http://localhost/Coconut/event/wiki/Specname1 Link1'
        task = easy_tasks[0]
        specs = []
        params = [path, task, specs, req]

        spec_name, specs = self.gr_api.get_specs_id_name_text(params)

        exp_spec_name = 'Specname1'

        exp_specs = [[2,
                      'Specname1',
                      u'Lorem ipsum dolor sit amet,\nconsetetur' +\
                      ' sadipscing elitr, sed diam nonumy eirmod' +\
                      ' tempor\ninvidunt ut labore et dolore magna' +\
                      ' aliquyam erat, sed diam\nvoluptua.']]

        self.assertEqual(
            spec_name,
            exp_spec_name,
            "Selected spec names do not match!")

        self.assertEqual(
            specs,
            exp_specs,
            "Selected specs do not match!")

        path = 'http://localhost/Coconut/event/wiki/Specname2'
        task = easy_tasks[1]
        specs = []
        params = [path, task, specs, req]

        spec_name, specs = self.gr_api.get_specs_id_name_text(params)

        exp_spec_name = 'Specname2'

        exp_specs = [[3, 'Specname2', u'At vero eos et accusam' +\
                      ' et justo duo dolores et\nea rebum. Stet' +\
                      ' clita kasd gubergren, no sea takimata \n' +\
                      'sanctus est Lorem ipsum dolor sit amet.']]

        self.assertEqual(
            spec_name,
            exp_spec_name,
            "Selected spec names do not match!")

        self.assertEqual(
            specs,
            exp_specs,
            "Selected specs do not match!")

        path = 'http://localhost/Coconut/event/wiki/Specname3|Link3'
        task = easy_tasks[2]
        specs = []
        params = [path, task, specs, req]

        spec_name, specs = self.gr_api.get_specs_id_name_text(params)

        exp_spec_name = 'Specname3'

        exp_specs = [[4,
                      'Specname3',
                      u'Lorem ipsum dolor sit amet,\n' +\
                      'consetetur sadipscing elitr, sed' +\
                      ' diam nonumy eirmod tempor\ninvidunt' +\
                      ' ut labore et dolore magna aliquyam erat,' +\
                      ' sed diam\nvoluptua.']]

        self.assertEqual(
            spec_name,
            exp_spec_name,
            "Selected spec names do not match!")

        self.assertEqual(
            specs,
            exp_specs,
            "Selected specs do not match!")

        path = 'http://localhost/Coconut/event/wiki/Specname4'
        task = easy_tasks[2]
        specs = []
        params = [path, task, specs, req]

        spec_name, specs = self.gr_api.get_specs_id_name_text(params)

        exp_spec_name = 'Specname4'

        exp_specs = [[4,
                      'Specname4',
                      u'At vero eos et accusam et justo' +\
                      ' duo dolores et\nea rebum. Stet' +\
                      ' clita kasd gubergren, no sea' +\
                      ' takimata\nsanctus est Lorem ipsum' +\
                      ' dolor sit amet.']]

        self.assertEqual(
            spec_name,
            exp_spec_name,
            "Selected spec names do not match!")

        self.assertEqual(
            specs,
            exp_specs,
            "Selected specs do not match!")

        path = 'e:/wiki/Specname1'
        task = easy_tasks[4]
        specs = []
        params = [path, task, specs, req]

        spec_name, specs = self.gr_api.get_specs_id_name_text(params)

        exp_spec_name = 'Specname1'

        exp_specs = [[2,
                      'Specname1',
                      u'Lorem ipsum dolor sit amet,\n' +\
                      'consetetur sadipscing elitr,' +\
                      ' sed diam nonumy eirmod tempor\n' +\
                      'invidunt ut labore et dolore' +\
                      ' magna aliquyam erat, sed diam\n' +\
                      'voluptua.']]

        self.assertEqual(
            spec_name,
            exp_spec_name,
            "Selected spec names do not match!")

        self.assertEqual(
            specs,
            exp_specs,
            "Selected specs do not match!")

        path = 'e:/wiki/Specname2|Specname2'
        task = easy_tasks[5]
        specs = []
        params = [path, task, specs, req]

        spec_name, specs = self.gr_api.get_specs_id_name_text(params)

        exp_spec_name = 'Specname2'

        exp_specs = [[3,
                      'Specname2',
                      u'At vero eos et accusam et justo' +\
                      ' duo dolores et\nea rebum. Stet' +\
                      ' clita kasd gubergren, no sea' +\
                      ' takimata \nsanctus est Lorem'+\
                      ' ipsum dolor sit amet.']]

        self.assertEqual(
            spec_name,
            exp_spec_name,
            "Selected spec names do not match!")

        self.assertEqual(
            specs,
            exp_specs,
            "Selected specs do not match!")

        self.gr_api.errorlog = []
        path = 'http://localhost/Coconut/event/wiki/Specname5'
        task = easy_tasks[3]
        specs = []
        params = [path, task, specs, req]

        spec_name, specs = self.gr_api.get_specs_id_name_text(params)

        errorlog = [('APO spec does not exist.' +\
                     ' Create APO spec: Specname5\n',
                     'http://example.org/Coconut/task/ticket/5',
                     'http://example.org/Coconut/event/wiki/Specname5')]

        self.assertEqual(
            self.gr_api.errorlog,
            errorlog,
            "Errorlogs do not match!")

        self.gr_api.errorlog = []
        path = 'http://localhost/Coconut/event/Specname4'
        task = easy_tasks[3]
        specs = []
        params = [path, task, specs, req]

        spec_name, specs = self.gr_api.get_specs_id_name_text(params)

        errorlog = [('Spec link has non-standard path.' +\
                     ' Move spec [[http://localhost/' +\
                     'Coconut/event/wiki/Specname4]]'+\
                     ' to http://example.org/Coconut/' +\
                     'event/wiki/{spec_name}',
                     'http://example.org/Coconut/task/ticket/5',
                     'http://example.org/Coconut/event/wiki/APO')]

        self.assertEqual(
            self.gr_api.errorlog,
            errorlog,
            "Errorlogs do not match!")

    def test_get_specs(self):
        """ Test get_specs """

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []
        env = self.gr_api.envs['task']

        req = MockRequest(self.gr_api.envs['task'])

        self.tktids = self._insert_tickets(
            self.gr_api.envs['task'],
            owner=[None, '', 'someone', 'someone_else', 'none'],
            type=[None, '', 'enhancement', 'defect', 'task'],
            status=[None, '', 'new', 'assigned',
                    'reopened', 'reviewing', 'closed'],
            milestone=[None, '', 'bar', 'baz'])
        when = datetime(2008, 8, 1, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 2,
                       'alice', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 3,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 4,
                       'bob', when, type='easy', status='reviewing')
        _modify_ticket(self.gr_api.envs['task'], 5,
                       'bob', when, type='easy', status='reviewing')
        when = datetime(2008, 8, 2, 12, 34, 56, 987654, utc)
        _modify_ticket(self.gr_api.envs['task'], 1,
                       'bob', when, status='closed')

        with env.db_transaction as dtb:
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[1], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[2], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[3], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[4], self.tktids[5]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[5], self.tktids[6]))
            dtb("INSERT INTO mastertickets (source,dest) VALUES ('{}','{}')"\
                .format(self.tktids[6], self.tktids[7]))

        easy_tasks = [
            (2, u'Summary 1', u'easy', u'reviewing', None, None,
             None, None, None, None, None, None,
             '[http://localhost/Coconut/event/wiki/Specname1 Specname1]',
             None, None, None, None, None),
            (3, u'Summary 2', u'easy', u'reviewing', None, None,
             u'someone', None, None, None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname2| Specname2 ]]',
             None, None, None, None, u'bar'),
            (4, u'Summary 3', u'easy', u'reviewing', None, None,
             u'someone_else', None, None, None, None, None,
             '[http://localhost/Coconut/event/wiki/Specname3  Specname3]',
             None, None, None, None, u'baz'),
            (5, u'Summary 4', u'easy', u'reviewing', None, None,
             u'none', u'bob', u'2008-08-01', None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname4|Specname4]]',
             None, None, None, None, None)]

        pages = {
            'Specname1': """Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
invidunt ut labore et dolore magna aliquyam erat, sed diam
voluptua.""",
            'Specname2': """At vero eos et accusam et justo duo dolores et
ea rebum. Stet clita kasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet.""",
            'Specname3': """Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
invidunt ut labore et dolore magna aliquyam erat, sed diam
voluptua.""",
            'Specname4': """At vero eos et accusam et justo duo dolores et
ea rebum. Stet clita kasd gubergren, no sea takimata
sanctus est Lorem ipsum dolor sit amet."""}
        _insert_wiki_pages(self.gr_api.envs['event'], pages)

        easy_specs = [
            [2,
             'Specname1',
             u'Lorem ipsum dolor sit amet,\nconsetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.'],
            [3,
             'Specname2',
             u'At vero eos et accusam et justo duo dolores et\nea rebum.' +\
             ' Stet clita kasd gubergren, no sea takimata \nsanctus est' +\
             ' Lorem ipsum dolor sit amet.'],
            [4,
             'Specname3',
             u'Lorem ipsum dolor sit amet,\nconsetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.'],
            [5,
             'Specname4',
             u'At vero eos et accusam et justo duo dolores et\nea rebum.' +\
             ' Stet clita kasd gubergren, no sea takimata\nsanctus est' +\
             ' Lorem ipsum dolor sit amet.']]

        self.assertEqual(
            self.gr_api.get_specs(easy_tasks, req),
            easy_specs,
            "Selected specs do not match!")

        easy_tasks = [
            (2, u'Summary 1', u'easy', u'reviewing', None, None,
             None, None, None, None, None, None,
             '[http://localhost/Coconut/event/wiki/Specname1 Specname1]',
             None, None, None, None, None),
            (3, u'Summary 2', u'easy', u'reviewing', None, None,
             u'someone', None, None, None, None, None,
             None,
             None, None, None, None, u'bar'),
            (4, u'Summary 3', u'easy', u'reviewing', None, None,
             u'someone_else', None, None, None, None, None,
             '[http://localhost/Coconut/event/wiki/Specname3  Specname3]',
             None, None, None, None, u'baz'),
            (5, u'Summary 4', u'easy', u'reviewing', None, None,
             u'none', u'bob', u'2008-08-01', None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname4|Specname4]]',
             None, None, None, None, None)]

        self.gr_api.get_specs(easy_tasks, req)

        errorlog = [('Link to spec is empty.' +\
                     ' Create a link to spec 3, Summary 2\n',
                     'http://example.org/Coconut/task/ticket/3',
                     'http://example.org/Coconut/event/wiki/Specname1')]

        self.assertEqual(
            self.gr_api.errorlog,
            errorlog,
            "Errorlogs do not match!")

    def test_get_header_text_from_specs(self):
        """ Test get_spec_section and
        get_header_text_from_specs """

        # Empty the list (other unittests also use this list)
        self.gr_api.errorlog = []

        start = r"^=Lorem ipsum dolor sit amet,"
        end = r"^=Lorem ipsum consetetur sadipscing elitr,"
        header_start = r"=Lorem ipsum dolor sit amet,"
        header_end = r"=Lorem ipsum consetetur sadipscing elitr,"
        easy_specs = [
            [2,
             'Specname1',
             u'=Lorem ipsum dolor sit amet,\nconsetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.\n' +\
             '=Lorem ipsum consetetur sadipscing elitr,\n' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.'],
            [3,
             'Specname2',
             u'=Lorem ipsum dolor sit amet,\nconsetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.\n' +\
             '=Lorem ipsum consetetur sadipscing elitr,\n' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.']]

        section_lorem_ipsum = [
            [2,
             'Specname1',
             'consetetur sadipscing elitr, sed diam nonumy ' +\
             'eirmod tempor\ninvidunt ut labore et dolore ' +\
             'magna aliquyam erat, sed diam\nvoluptua.\n'],
            [3,
             'Specname2',
             'consetetur sadipscing elitr, sed diam nonumy ' +\
             'eirmod tempor\ninvidunt ut labore et dolore ' +\
             'magna aliquyam erat, sed diam\nvoluptua.\n']]

        req = MockRequest(self.gr_api.envs['task'])

        info = [easy_specs,
                start,
                end,
                header_start,
                header_end,
                req]

        self.assertEqual(
            self.gr_api.get_header_text_from_specs(info),
            section_lorem_ipsum,
            "Extracted spec sections do not match!")

        self.gr_api.errorlog = []
        start = r"^=Lorem ipsum dolor sit amet,"
        end = r"^=Lorem ipsum consetetur sadipscing elitr,"
        header_start = r"=Lorem ipsum dolor sit amet,"
        header_end = r"=Lorem ipsum consetetur sadipscing elitr,"
        easy_specs = [
            [2,
             'Specname1',
             u'consetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.\n' +\
             '=Lorem ipsum consetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.'],
            [3,
             'Specname2',
             u'Lorem ipsum dolor sit amet,\nconsetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.\n' +\
             '=Lorem ipsum consetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.']]

        info = [easy_specs,
                start,
                end,
                header_start,
                header_end,
                req]

        self.gr_api.get_header_text_from_specs(info)

        errorlog = [("Cannot find the header in the spec text." +\
                     " Please check spelling & special characters." +\
                     " Regex engine will match the following header:" +\
                     " '=Lorem ipsum dolor sit amet,'",
                     'http://example.org/Coconut/task/ticket/2',
                     'http://example.org/Coconut/event/wiki/Specname1'),
                    ("Cannot find the header in the spec text." +\
                     " Please check spelling & special characters." +\
                     " Regex engine will match the following header:" +\
                     " '=Lorem ipsum dolor sit amet,'",
                     'http://example.org/Coconut/task/ticket/3',
                     'http://example.org/Coconut/event/wiki/Specname2')]

        self.assertEqual(self.gr_api.errorlog, errorlog,
                         "Errorlogs do not match!")

        self.gr_api.errorlog = []
        start = r"^=Lorem ipsum dolor sit amet,"
        end = r"^=Lorem ipsum consetetur sadipscing elitr,"
        header_start = r"=Lorem ipsum dolor sit amet,"
        header_end = r"=Lorem ipsum consetetur sadipscing elitr,"
        easy_specs = [
            [2,
             'Specname1',
             u'=Lorem ipsum dolor sit amet,\nconsetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.\n' +\
             '=Lorem ipsum\n' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.'],
            [3,
             'Specname2',
             u'=Lorem ipsum dolor sit amet,\nconsetetur sadipscing elitr,' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.\n' +\
             '=Lorem ipsum consetetur sadipscing elitr,\n' +\
             ' sed diam nonumy eirmod tempor\ninvidunt ut labore et ' +\
             'dolore magna aliquyam erat, sed diam\nvoluptua.']]

        info = [easy_specs,
                start,
                end,
                header_start,
                header_end,
                req]

        self.gr_api.get_header_text_from_specs(info)

        errorlog = [("Program is trying to match the spec text " +\
                     "between two headers. It CAN find the first " +\
                     "header but it CANNOT find the next header.\n\n" +\
                     "The next header defines the end of a section and" +\
                     " the beginning of a next section. Please check" +\
                     " spelling & special characters. Regex engine" +\
                     " could not find the following header:" +\
                     " '=Lorem ipsum consetetur sadipscing elitr,'",
                     'http://example.org/Coconut/task/ticket/2',
                     'http://example.org/Coconut/event/wiki/Specname1')]

        self.assertEqual(self.gr_api.errorlog, errorlog,
                         "Errorlogs do not match.")

    def test_get_wikipage(self):
        """ Test get_wikipage """

        pages = {
            'Specname1': """=Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
aliquyam erat, sed diam \n[[Image(Image2.jpg)])]\nvoluptua.""",
            'Specname2': """=Lorem ipsum dolor sit amet,
[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita 
[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet."""}

        _insert_wiki_pages(self.gr_api.envs['event'], pages)

        env = self.gr_api.envs['event']

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image_path below.

        spec_name = 'Specname1'
        page = self.gr_api.get_wikipage(spec_name)

        page_text = pages['Specname1']

        self.assertEqual(page.text,
                         page_text,
                         "Returned page text does not match")

    def test_get_image_file(self):
        """ Test get_image_file """

        pages = {
            'Specname1': """=Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
aliquyam erat, sed diam \n[[Image(Image2.jpg)])]\nvoluptua.""",
            'Specname2': """=Lorem ipsum dolor sit amet,
[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita 
[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet."""}

        _insert_wiki_pages(self.gr_api.envs['event'], pages)

        easy_specs = [
            [2,
             'Specname1',
             'consetetur sadipscing elitr, sed diam nonumy eirmod tempor\n' +\
             '[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna \n' +\
            'aliquyam erat, sed diam \n[[Image(Image2.jpg)]]\nvoluptua.\n'],
            [3,
             'Specname2',
             '[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita \n' +\
             '[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata \n' +\
             'sanctus est Lorem ipsum dolor sit amet.\n']]

        env = self.gr_api.envs['event']

        req = MockRequest(self.gr_api.envs['task'])

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image_path below.

        spec = 'Specname1'
        page = WikiPage(self.gr_api.envs['event'], spec)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)
        attachment.insert('Image1.jpg', StringIO(''), 0)
        attachment.insert('Image2.jpg', StringIO(''), 0)

        spec = 'Specname2'
        page = WikiPage(self.gr_api.envs['event'], spec)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)

        attachment.insert('Image1.jpg', StringIO(''), 0)
        attachment.insert('Image2.jpg', StringIO(''), 0)

        filename = 'Image1.jpg'
        image_path = unicode(env.path, "utf-8")+\
            u'/files/attachments/wiki/bdc/bdc72' +\
            '6f49cd502d4306404b090a5ddd13bb7dc0e/' +\
            '98c78c01ccdb21a78fd4f561e980ccd4d3a5a685.jpg'

        self.assertEqual(
            self.gr_api.get_image_file(filename,
                                       easy_specs[0][1],
                                       req),
            image_path,
            "Returned image_path value does not match" +\
            " for filename:{}!".format(filename))

        filename = 'Image2.jpg'

        image_path = unicode(env.path, "utf-8")+\
            u'/files/attachments/wiki/bdc/bdc72' +\
            '6f49cd502d4306404b090a5ddd13bb7dc0e/' +\
            'e8385af6dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'

        self.assertEqual(
            self.gr_api.get_image_file(filename,
                                       easy_specs[0][1],
                                       req),
            image_path,
            "Returned image_path value does not match" +\
            " for filename:{}!".format(filename))

        self.gr_api.errorlog = []
        filename = 'Image1.jpg'
        spec = 'Specname3'
        self.gr_api.get_image_file(filename, spec, req)

        errorlog = [('Page for the spec Specname3' +\
                     ' could not be found!',
                     0,
                     'http://example.org/Coconut/' +\
                     'event/wiki/Specname3')]

        self.assertEqual(self.gr_api.errorlog,
                         errorlog,
                         "Errorlog does not match for " +\
                         "spec: {}".format(spec))

        self.gr_api.errorlog = []
        filename = 'Image4.jpg'
        self.gr_api.get_image_file(filename,
                                   easy_specs[0][1],
                                   req)
        errorlog = [('Attachment Image4.jpg could' +\
                     ' not be found at Specname1',
                     0,
                     'http://example.org/Coconut/event/wiki/Specname1')]
        self.assertEqual(self.gr_api.errorlog,
                         errorlog,
                         "Errorlog does not match for " +\
                         "spec: {}".format(easy_specs[0][1]))

    def test_get_sections_with_images(self):
        """ Test get_sections_with_images and
        get_image_file """

        pages = {
            'Specname1': """=Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
aliquyam erat, sed diam \n[[Image(Image2.jpg)])]\nvoluptua.""",
            'Specname2': """=Lorem ipsum dolor sit amet,
[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita 
[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet."""}

        _insert_wiki_pages(self.gr_api.envs['event'], pages)

        easy_specs = [
            [2,
             'Specname1',
             'consetetur sadipscing elitr, sed diam nonumy eirmod tempor\n' +\
             '[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna \n' +\
            'aliquyam erat, sed diam \n[[Image(Image2.jpg)]]\nvoluptua.\n'],
            [3,
             'Specname2',
             '[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita \n' +\
             '[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata \n' +\
             'sanctus est Lorem ipsum dolor sit amet.\n']]

        env = self.gr_api.envs['event']

        req = MockRequest(self.gr_api.envs['task'])

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')

        spec = 'Specname1'
        page = WikiPage(self.gr_api.envs['event'], spec)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)
        attachment.insert('Image1.jpg', StringIO(''), 0)
        attachment.insert('Image2.jpg', StringIO(''), 0)

        spec = 'Specname2'
        page = WikiPage(self.gr_api.envs['event'], spec)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)

        attachment.insert('Image1.jpg', StringIO(''), 0)
        attachment.insert('Image2.jpg', StringIO(''), 0)

        # As an example
        # env.path = '/tmp/trac-tempenv-lIeyEP'
        # the value after 'trac-tempenv-' which is 'lIeyEP'
        # in this instance is generated randomly each time
        # the test runs so we have to insert env.path into
        # image dictionary below.
        easy_specs_with_img_attch = [
            [2,
             'Specname1',
             'consetetur sadipscing elitr, sed diam nonumy eirmod tempor\n' +\
             '[[Image(Image1.jpg)]]\n'+\
             'invidunt ut labore et dolore magna \n' +\
             'aliquyam erat, sed diam \n' +\
             '[[Image(Image2.jpg)]]\nvoluptua.\n',
             {'Image1.jpg': unicode(env.path, "utf-8")+\
              u'/files/attachments/wiki/bdc/bdc726f49cd502d4306404b090a5' +\
              'ddd13bb7dc0e/98c78c01ccdb21a78fd4f561e980ccd4d3a5a685.jpg',
              'Image2.jpg': unicode(env.path, "utf-8") +\
              u'/files/attachments/wiki/bdc/bdc726f49cd502d4306404b090a5' +\
              'ddd13bb7dc0e/e8385af6dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'}],
            [3,
             'Specname2',
             '[[Image(Image1.jpg)]]\n' +\
             'duo dolores et ea rebum. Stet clita \n' +\
             '[[Image(Image2.jpg)]]\n' +\
             'kasd gubergren, no sea takimata \n' +\
             'sanctus est Lorem ipsum dolor sit amet.\n',
             {'Image1.jpg': unicode(env.path, "utf-8") +\
              u'/files/attachments/wiki/973/97308985c7cb5b1e1f121a0823a0' +\
              'a33b380e8b11/98c78c01ccdb21a78fd4f561e980ccd4d3a5a685.jpg',
              'Image2.jpg': unicode(env.path, "utf-8") +\
              u'/files/attachments/wiki/973/97308985c7cb5b1e1f121a0823a0' +\
              'a33b380e8b11/e8385af6dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'}]]

        self.assertEqual(
            self.gr_api.get_sections_with_images(easy_specs, req),
            easy_specs_with_img_attch,
            "Extracted spec sections with images do not match!")

    def test_get_sections_with_tables(self):
        """ Test get_sections_with_tables and
        tables_in_spec_text """

        pages = {
            'Specname1': """=Lorem ipsum dolor sit amet,
consetetur sadipscing elitr, sed diam nonumy eirmod tempor
[[Image(Image1.jpg)]]\ninvidunt ut labore et dolore magna 
aliquyam erat, sed diam \n[[Image(Image2.jpg)])]\nvoluptua.
|| 1 || 2 || 3 ||
|||| 1-2 || 3 ||
|| 1 |||| 2-3 ||
|||||| 1-2-3 ||
=Lorem ipsum consetetur sadipscing elitr,""",
            'Specname2': """=Lorem ipsum dolor sit amet,
|| 1 || 2 || 3 ||
|||| 1-2 || 3 ||
|| 1 |||| 2-3 ||
|||||| 1-2-3 ||
[[Image(Image1.jpg)]]\nduo dolores et ea rebum. Stet clita 
[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata 
sanctus est Lorem ipsum dolor sit amet.
=Lorem ipsum consetetur sadipscing elitr,"""}

        _insert_wiki_pages(self.gr_api.envs['event'], pages)

        env = self.gr_api.envs['event']

        # use tempfile so as not to pollute the standard python2.7 area
        env.path = tempfile.mkdtemp(prefix='trac-tempenv-')

        spec = 'Specname1'
        page = WikiPage(self.gr_api.envs['event'], spec)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)
        attachment.insert('Image1.jpg', StringIO(''), 0)
        attachment.insert('Image2.jpg', StringIO(''), 0)

        spec = 'Specname2'
        page = WikiPage(self.gr_api.envs['event'], spec)
        attachment = Attachment(page.env,
                                page.realm,
                                page.resource.id)

        attachment.insert('Image1.jpg', StringIO(''), 0)
        attachment.insert('Image2.jpg', StringIO(''), 0)

        easy_specs = [
            [2,
             'Specname1',
             'consetetur sadipscing elitr, sed diam nonumy eirmod tempor\n' +\
             '[[Image(Image1.jpg)]]\n' +\
             'invidunt ut labore et dolore magna \n' +\
             'aliquyam erat, sed diam \n' +\
             '[[Image(Image2.jpg)]]\n' +\
             'voluptua.\n' +\
             '|| 1 || 2 || 3 ||\n' +\
             '|||| 1-2 || 3 ||\n' +\
             '|| 1 |||| 2-3 ||\n' +\
             '|||||| 1-2-3 ||\n',
             {'Image1.jpg': u'/tmp/trac-tempenv-WbQieJ/files/attachments/' +\
              'wiki/bdc/bdc726f49cd502d4306404b090a5ddd13bb7dc0e/98c78c01' +\
              'ccdb21a78fd4f561e980ccd4d3a5a685.jpg',
              'Image2.jpg': u'/tmp/trac-tempenv-WbQieJ/files/attachments/' +\
              'wiki/bdc/bdc726f49cd502d4306404b090a5ddd13bb7dc0e/e8385af6' +\
              'dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'}],
            [3,
             'Specname2',
             '|| 1 || 2 || 3 ||\n' +\
             '|||| 1-2 || 3 ||\n' +\
             '|| 1 |||| 2-3 ||\n' +\
             '|||||| 1-2-3 ||\n' +\
             '[[Image(Image1.jpg)]]\n' +\
             'duo dolores et ea rebum. Stet clita \n' +\
             '[[Image(Image2.jpg)]]\n' +\
             'kasd gubergren, no sea takimata \n' +\
             'sanctus est Lorem ipsum dolor sit amet.\n',
             {'Image1.jpg': u'/tmp/trac-tempenv-WbQieJ/files/attachments/' +\
              'wiki/973/97308985c7cb5b1e1f121a0823a0a33b380e8b11/98c78c01' +\
              'ccdb21a78fd4f561e980ccd4d3a5a685.jpg',
              'Image2.jpg': u'/tmp/trac-tempenv-WbQieJ/files/attachments/' +\
              'wiki/973/97308985c7cb5b1e1f121a0823a0a33b380e8b11/e8385af6' +\
              'dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'}]]

        easy_specs_with_table_attach = [
            [2,
             'Specname1',
             'consetetur sadipscing elitr, sed diam nonumy eirmod tempor\n' +\
             '[[Image(Image1.jpg)]]\n' +\
             'invidunt ut labore et dolore magna \n' +\
             'aliquyam erat, sed diam \n' +\
             '[[Image(Image2.jpg)]]\nvoluptua.\n',
             {'Image1.jpg': u'/tmp/trac-tempenv-WbQieJ/files/attachments/' +\
              'wiki/bdc/bdc726f49cd502d4306404b090a5ddd13bb7dc0e/98c78c01' +\
              'ccdb21a78fd4f561e980ccd4d3a5a685.jpg',
              'Image2.jpg': u'/tmp/trac-tempenv-WbQieJ/files/attachments/' +\
              'wiki/bdc/bdc726f49cd502d4306404b090a5ddd13bb7dc0e/e8385af6' +\
              'dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'},
             {'Table_11': [[[' 1 '], [' 2 '], [' 3 ']],
                           [[''], [' 1-2 '], [' 3 ']],
                           [[' 1 '], [''], [' 2-3 ']],
                           [['', ''], [' 1-2-3 ']]]}],
            [3,
             'Specname2',
             '[[Table(Table_21.tbl)]]\n' +\
             '[[Image(Image1.jpg)]]\n\n' +\
             'duo dolores et ea rebum. Stet clita \n' +\
             '[[Image(Image2.jpg)]]\nkasd gubergren, no sea takimata \n' +\
             'sanctus est Lorem ipsum dolor sit amet.\n',
             {'Image1.jpg': u'/tmp/trac-tempenv-WbQieJ/files/attachments/' +\
              'wiki/973/97308985c7cb5b1e1f121a0823a0a33b380e8b11/98c78c01' +\
              'ccdb21a78fd4f561e980ccd4d3a5a685.jpg',
              'Image2.jpg': u'/tmp/trac-tempenv-WbQieJ/files/attachments/' +\
              'wiki/973/97308985c7cb5b1e1f121a0823a0a33b380e8b11/e8385af6' +\
              'dfec928ba93ae7b6ccdc2c5f2fcb89f8.jpg'},
             {'Table_21': [[[' 1 '], [' 2 '], [' 3 ']],
                           [[''], [' 1-2 '], [' 3 ']],
                           [[' 1 '], [''], [' 2-3 ']],
                           [['', ''], [' 1-2-3 ']]]}]]

        self.assertEqual(
            get_sections_with_tables(easy_specs),
            easy_specs_with_table_attach,
            "Extracted spec sections with tables do not match!")

    def test_filter_regex(self):
        """ Test filter_wiki_text """

        text = r"'''Lorem ipsum''', \\"
        regex = r'(.*?)\\\\{1,}\s*$'
        flt_text = "'''Lorem ipsum''', "

        self.assertEqual(
            filter_regex(regex, text),
            flt_text,
            "Filtered text values do not" +\
            " match for regex:{}!".format(regex))

        text = r"'''Lorem ipsum''', \\\\ "
        regex = r'(.*?)\\\\{1,}\s*$'
        flt_text = "'''Lorem ipsum''', "

        self.assertEqual(
            filter_regex(regex, text),
            flt_text,
            "Filtered text values do not" +\
            " match for regex:{}!".format(regex))

        text = r"=Lorem ipsum = "
        regex = r'^\s*=\s*(.*?)\s*=\s*$'
        flt_text = "Lorem ipsum"

        self.assertEqual(
            filter_regex(regex, text),
            flt_text,
            "Filtered text values do not" +\
            " match for regex:{}!".format(regex))

        text = r" = Lorem ipsum    ="
        regex = r'^\s*=\s*(.*?)\s*=\s*$'
        flt_text = "Lorem ipsum"

        self.assertEqual(
            filter_regex(regex, text),
            flt_text,
            "Filtered text values do not" +\
            " match for regex:{}!".format(regex))

    def test_filter_multi_regex(self): # pylint: disable=no-self-use
        """ Test filter_wiki_text """

        text = """ '''Lorem ipsum''', **dolor**
 sed diam **A'^xy^**, **A',,xz,,** and '''A',,yz,,''' """

        text = text.replace('\n', ' ')

        for flt in FILTER_STYLES:
            text = filter_multi_regex(flt[0], flt[1], text)

    def test_filter_wiki_text(self):
        """ Test filter_wiki_text """

        text = """ '''Lorem ipsum''', **dolor** sit amet, [=#Ref1]
consetetur [=#Fig8] sadipscing elitr, L, LT or ST^'''{{{*****}}}'''^
sed diam **A',,yz,,**  nonumy eirmod [[BR]] tempor invidunt [=#Table5]
ut labore et dolore magna aliquyam erat, sed diam voluptua."""

        text = text.replace('\n', ' ')

        flt_text = """ '''Lorem ipsum''', **dolor** sit amet, Ref1
 consetetur [=#Fig8] sadipscing elitr, L, LT or ST^'''*****'''^ sed
 diam **A',,yz,,**  nonumy eirmod [[BR]] tempor invidunt [=#Table5]
 ut labore et dolore magna aliquyam erat, sed diam voluptua."""

        self.assertEqual(
            filter_wiki_text(text),
            flt_text.replace('\n', ''),
            "Filtered text values do not match!")

    def test_check_for_relative_link(self):
        """ Test check_for_relative_link """

        hypermatches = [('', '../', 'GPD/Damage_Tolerance',
                         '|DT-GPD]]', 'DT-GPD'),
                        ('', '../', 'GPD/Composite_Joint',
                         '|FH-GPD]]', 'FH-GPD'),
                        ('', '../', 'GPD/Material_Strength',
                         '|MS-GPD]]', 'MS-GPD'),
                        ('', '../', 'GPD/Metallic_Joint',
                         '|MBJ-GPD]]', 'MBJ-GPD')]

        hyperlists = check_for_relative_link(hypermatches)

        exp_hyperlists = [('', '', 'GPD/Damage_Tolerance',
                           '|DT-GPD]]', 'DT-GPD'),
                          ('', '', 'GPD/Composite_Joint',
                           '|FH-GPD]]', 'FH-GPD'),
                          ('', '', 'GPD/Material_Strength',
                           '|MS-GPD]]', 'MS-GPD'),
                          ('', '', 'GPD/Metallic_Joint',
                           '|MBJ-GPD]]', 'MBJ-GPD')]

        self.assertEqual(
            hyperlists,
            exp_hyperlists,
            "list of hypermatches do not match!")

        hypermatches = [('', '../test', 'GPD/Damage_Tolerance',
                         '|DT-GPD]]', 'DT-GPD'),
                        ('', '../test/test2', 'GPD/Composite_Joint',
                         '|FH-GPD]]', 'FH-GPD'),
                        ('', '../$data/test', 'GPD/Material_Strength',
                         '|MS-GPD]]', 'MS-GPD'),
                        ('', '../http://', 'GPD/Metallic_Joint',
                         '|MBJ-GPD]]', 'MBJ-GPD')]

        hyperlists = check_for_relative_link(hypermatches)

        exp_hyperlists = [('', 'test', 'GPD/Damage_Tolerance',
                           '|DT-GPD]]', 'DT-GPD'),
                          ('', 'test/test2', 'GPD/Composite_Joint',
                           '|FH-GPD]]', 'FH-GPD'),
                          ('', '$data/test', 'GPD/Material_Strength',
                           '|MS-GPD]]', 'MS-GPD'),
                          ('', 'http://', 'GPD/Metallic_Joint',
                           '|MBJ-GPD]]', 'MBJ-GPD')]

        for i, hyper in enumerate(hyperlists):
            self.assertEqual(
                hyper[1],
                exp_hyperlists[i][1],
                "hyperlists do not match!")

        self.assertEqual(
            hyperlists,
            exp_hyperlists,
            "list of hypermatches do not match!")

        hypermatches = [('', '../', 'GPD/Damage_Tolerance',
                         '|DT-GPD]]', 'DT-GPD')]

        hyperlist = check_for_relative_link(hypermatches)

        exp_hyperlist = [('', '', 'GPD/Damage_Tolerance',
                          '|DT-GPD]]', 'DT-GPD')]

        self.assertEqual(
            hyperlist,
            exp_hyperlist,
            "hypermatches do not match!")

        # TESTING TO SEE IF hypermatches list
        # REMAINS THE SAME IF "../" NOT FOUND
        hypermatches = [(" '''Lorem ipsum''', **dolor** sit amet, Ref1 ",
                         'Dummy-APO-Database/',
                         'GPD/Material_Strength', '| MS-GPD]]', ' MS-GPD'),
                        (' consetetur [=#Fig8] sadipscing elitr, L, LT or ST ',
                         '/', 'GPD/Material_Strength',
                         '| MS-GPD]]', ' MS-GPD'),
                        ("  sed diam **A',,yz,,**nonumy ", 'GPD/',
                         'Material_Strength', '| MS-GPD]]', ' MS-GPD'),
                        (' eirmod  ', 'BR]] [[/',
                         'IP006/Dummy-APO-Database/GPD/Material_Strength',
                         '| MS-GPD]]', ' MS-GPD'),
                        ('tempor invidunt [=#Table5] ut labore' +\
                         ' et dolore magna aliquyam erat tempor invidunt ',
                         'IP006/', 'Dummy-APO-Database/GPD/Material_Strength',
                         '| MS-GPD]]', ' MS-GPD'),
                        (' ', '/', 'GPD/Material_Strength',
                         '| MS-GPD]]', ' MS-GPD'),
                        (', ut labore ', '/', 'GPD/Material_Strength',
                         '| MS-GPD]]', ' MS-GPD')]

        exp_hypermatches = check_for_relative_link(hypermatches)

        self.assertEqual(
            hypermatches,
            exp_hypermatches,
            "hypermatches do not match!")

    def test_find_hyperlinks(self):
        """ Test find_hyperlinks """

        # TYPE 1, DOUBLE BRACKETS
        text = """ '''Lorem ipsum''', **dolor** sit amet, [=#Ref1]
([[""" + r"file:///\\lorem\data$\Ipsum\PLM|Link" + """]]) consetetur [=#Fig8]
 sadipscing elitr, L, LT or ST^'''{{{*****}}}'''^ 
[[http://lorem/ipsum/app/doc1|PLM Light]]  sed diam **A',,yz,,** 
nonumy [[http://lorem/ipsum/app/doc2|PLM Light]] eirmod  [[BR]] 
[[/wiki/test/spec|link1]] ut labore et dolore [[e:/wiki/test/spec|link2]] 
tempor invidunt [=#Table5] ut labore et dolore  magna aliquyam erat 
tempor invidunt [[wiki:/test/spec]] ut labore [[wiki:/test/spec|link3]] aliquyam erat 
[[/wiki/test/spec]], ut labore [[e:/wiki/test/spec]] sed diam voluptua."""

        text = text.replace('\n', '')

        exp_hypermatches = [(" '''Lorem ipsum''', **dolor** sit amet, Ref1(",
                             'file:', '///\\\\lorem\\data$\\Ipsum\\PLM',
                             '|Link]]', 'Link'),
                            (") consetetur [=#Fig8] sadipscing elitr," +\
                             " L, LT or ST^'''*****'''^ ",
                             'http:', '//lorem/ipsum/app/doc1',
                             '|PLM Light]]', 'PLM Light'),
                            ("  sed diam **A',,yz,,** nonumy ",
                             'http:', '//lorem/ipsum/app/doc2',
                             '|PLM Light]]', 'PLM Light'),
                            (' eirmod  [[BR]] ', '/wiki/',
                             'test/spec', '|link1]]',
                             'link1'),
                            (' ut labore et dolore ', 'e:/wiki/',
                             'test/spec', '|link2]]', 'link2'),
                            (' tempor invidunt [=#Table5] ut labore et' +\
                             ' dolore  magna aliquyam erat tempor invidunt ',
                             'wiki:', '/test/spec', ']]', ''),
                            (' ut labore ', 'wiki:', '/test/spec',
                             '|link3]]', 'link3'),
                            (' aliquyam erat ', '/wiki/',
                             'test/spec', ']]', ''),
                            (', ut labore ', 'e:/wiki/',
                             'test/spec', ']]', ''),
                            ' sed diam voluptua.']

        _, hypermatches = find_hyperlinks(filter_wiki_text(text))

        self.assertEqual(
            exp_hypermatches,
            hypermatches,
            "hypermatches lists do not match!")

        # TYPE 2, SINGLE BRACKETS
        text = """ '''Lorem ipsum''', **dolor** sit amet, [=#Ref1]
([""" + r"file:///\\lorem\data$\Ipsum\PLM Link" + """]) consetetur [=#Fig8]
 sadipscing elitr, L, LT or ST^'''{{{*****}}}'''^ 
[http://lorem/ipsum/app/doc1 PLM Light] sed diam **A',,yz,,** 
nonumy [http://lorem/ipsum/app/doc2 PLM Light] eirmod  [[BR]] 
tempor [wiki:/test/spec APO link] labore magna aliquyam erat, 
tempor [wiki:/test/spec] labore magna aliquyam erat, 
[e:/wiki/test/spec APO link] et dolore magna aliquyam erat, 
[e:/wiki/test/spec] et dolore magna aliquyam erat, 
[/wiki/test/spec APO link] sed diam.
sed diam [/wiki/test/spec] voluptua."""

        text = text.replace('\n', '')

        exp_hypermatches = [(" '''Lorem ipsum''', **dolor** sit amet, Ref1(",
                             'file:', '///\\\\lorem\\data$\\Ipsum\\PLM',
                             ' Link]', 'Link'),
                            (") consetetur [=#Fig8] sadipscing" +\
                             " elitr, L, LT or ST^'''*****'''^ ",
                             'http:', '//lorem/ipsum/app/doc1',
                             ' PLM Light]', 'PLM Light'),
                            (" sed diam **A',,yz,,** nonumy ",
                             'http:', '//lorem/ipsum/app/doc2',
                             ' PLM Light]', 'PLM Light'),
                            (' eirmod  [[BR]] tempor ', 'wiki:',
                             '/test/spec', ' APO link]', 'APO link'),
                            (' labore magna aliquyam erat, tempor ',
                             'wiki:', '/test/spec', ']', ''),
                            (' labore magna aliquyam erat, ',
                             'e:/wiki/', 'test/spec',
                             ' APO link]', 'APO link'),
                            (' et dolore magna aliquyam erat, ',
                             'e:/wiki/', 'test/spec', ']', ''),
                            (' et dolore magna aliquyam erat, ',
                             '/wiki/', 'test/spec',
                             ' APO link]', 'APO link'),
                            (' sed diam.sed diam ',
                             '/wiki/', 'test/spec', ']', ''),
                            ' voluptua.']

        _, hypermatches = find_hyperlinks(filter_wiki_text(text))

        self.assertEqual(
            exp_hypermatches,
            hypermatches,
            "hypermatches lists do not match!")

        # TYPE 3, NO BRACKETS
        text = """ '''Lorem ipsum''', **dolor** sit amet, [=#Ref1]
 L, LT or ST^'''{{{*****}}}'''^ 
http://lorem/ipsum/app/doc1 sed diam **A',,yz,,** 
nonumy http://lorem/ipsum/app/doc2 eirmod  [[BR]] 
tempor wiki:/test/spec APO labore magna aliquyam erat, 
tempor wiki:/test/spec labore magna aliquyam erat, 
e:/wiki/test/spec et dolore magna aliquyam erat, 
tempor e:/wiki/test/spec et dolore magna aliquyam, 
/wiki/test/spec sed diam.
sed diam /wiki/test/spec voluptua."""

        text = text.replace('\n', '')

        exp_hypermatches = [(" '''Lorem ipsum''', **dolor** sit" +\
                             " amet, Ref1 L, LT or ST^'''*****'''^ ",
                             'http:', '//lorem/ipsum/app/doc1',
                             ' ', '', ' '),
                            ("sed diam **A',,yz,,** nonumy ",
                             'http:', '//lorem/ipsum/app/doc2',
                             ' ', '', ' '),
                            ('eirmod  [[BR]] tempor ', 'wiki:',
                             '/test/spec', ' ', '', ' '),
                            ('APO labore magna aliquyam erat, tempor ',
                             'wiki:', '/test/spec', ' ', '', ' '),
                            ('labore magna aliquyam erat, ',
                             'e:/wiki/', 'test/spec', ' ', '', ' '),
                            ('et dolore magna aliquyam erat, tempor ',
                             'e:/wiki/', 'test/spec', ' ', '', ' '),
                            ('et dolore magna aliquyam, ', '/wiki/',
                             'test/spec', ' ', '', ' '),
                            ('sed diam.sed diam ', '/wiki/',
                             'test/spec', ' ', '', ' '), 'voluptua.']

        _, hypermatches = find_hyperlinks(filter_wiki_text(text))

        self.assertEqual(
            exp_hypermatches,
            hypermatches,
            "hypermatches lists do not match!")

        # TYPE 4, r:#ID
        text = """ '''Lorem ipsum''', **dolor** sit amet, [=#Ref1]
 L, LT or ST^'''{{{*****}}}'''^ 
r:#805 sed diam **A',,yz,,** 
nonumy r:#806 eirmod  [[BR]] 
tempor r:#807 labore magna aliquyam erat, 
tempor r:#808 labore magna aliquyam erat, 
r:#809 et dolore magna aliquyam erat, 
tempor r:#810 et dolore magna aliquyam, 
r:#811 sed diam.
sed diam r:#812 voluptua."""

        text = text.replace('\n', '')

        _, hypermatches = find_hyperlinks(filter_wiki_text(text))

        exp_hypermatches = [(" '''Lorem ipsum''', **dolor** sit amet," +\
                             " Ref1 L, LT or ST^'''*****'''^ ",
                             'r:#', '805', ' ', 'r:#805'),
                            ("sed diam **A',,yz,,** nonumy ",
                             'r:#', '806', ' ', 'r:#806'),
                            ('eirmod  [[BR]] tempor ',
                             'r:#', '807', ' ', 'r:#807'),
                            ('labore magna aliquyam erat, tempor ',
                             'r:#', '808', ' ', 'r:#808'),
                            ('labore magna aliquyam erat, ',
                             'r:#', '809', ' ', 'r:#809'),
                            ('et dolore magna aliquyam erat, tempor ',
                             'r:#', '810', ' ', 'r:#810'),
                            ('et dolore magna aliquyam, ',
                             'r:#', '811', ' ', 'r:#811'),
                            ('sed diam.sed diam ',
                             'r:#', '812', ' ', 'r:#812'),
                            'voluptua.']

        self.assertEqual(
            hypermatches,
            exp_hypermatches,
            "hypermatches lists do not match!")

        # TYPE 5, DOUBLE BRACKETS WITH LINKS TO ANOTHER
        # PAGE UNDER SAME PARENT DIRECTORY
        text = """ '''Lorem ipsum''', **dolor** sit amet, [=#Ref1]
 [[Dummy-APO-Database/GPD/Material_Strength| MS-GPD]]
 consetetur [=#Fig8] sadipscing elitr, L, LT or ST
 [[/GPD/Material_Strength| MS-GPD]]  sed diam **A',,yz,,**
nonumy [[GPD/Material_Strength| MS-GPD]] eirmod  [[BR]]
 [[/IP006/Dummy-APO-Database/GPD/Material_Strength| MS-GPD]]
tempor invidunt [=#Table5] ut labore et dolore
 magna aliquyam erat tempor invidunt
 [[IP006/Dummy-APO-Database/GPD/Material_Strength| MS-GPD]]
 [[/GPD/Material_Strength| MS-GPD]], ut labore
 [[/GPD/Material_Strength| MS-GPD]] sed diam voluptua."""

        text = text.replace('\n', '')

        exp_hypermatches = [(" '''Lorem ipsum''', " +\
                             "**dolor** sit amet, Ref1 ",
                             'Dummy-APO-Database/',
                             'GPD/Material_Strength',
                             '| MS-GPD]]',
                             ' MS-GPD'),
                            (' consetetur [=#Fig8] ' +\
                             'sadipscing elitr, L, LT or ST ',
                             '/',
                             'GPD/Material_Strength',
                             '| MS-GPD]]',
                             ' MS-GPD'),
                            ("  sed diam **A',,yz,,**nonumy ",
                             'GPD/',
                             'Material_Strength',
                             '| MS-GPD]]',
                             ' MS-GPD'),
                            (' eirmod  ',
                             'BR]] [[/',
                             'IP006/Dummy-APO-Database/GPD/' +\
                             'Material_Strength',
                             '| MS-GPD]]',
                             ' MS-GPD'),
                            ('tempor invidunt [=#Table5] ut labore' +\
                             ' et dolore magna aliquyam erat' +\
                             ' tempor invidunt ',
                             'IP006/',
                             'Dummy-APO-Database/GPD/' +\
                             'Material_Strength',
                             '| MS-GPD]]',
                             ' MS-GPD'),
                            (' ',
                             '/',
                             'GPD/Material_Strength',
                             '| MS-GPD]]',
                             ' MS-GPD'),
                            (', ut labore ',
                             '/',
                             'GPD/Material_Strength',
                             '| MS-GPD]]',
                             ' MS-GPD'),
                            ' sed diam voluptua.']

        _, hypermatches = find_hyperlinks(filter_wiki_text(text))

        self.assertEqual(
            exp_hypermatches,
            hypermatches,
            "hypermatches do not match!")

        # TESTING LINKS WITH SPACES IN THEM
        # pylint: disable=anomalous-backslash-in-string
        text = "Storage of Data: [[file://\\en.tp.firm\Diam" +\
            "$\Com\SED_Dolore\Magna-Aliquyam_PEDx" +\
            "\006 lorem ipsum dolor sit amet" +\
            "\02 labore magna\P6\SED-Wizard" +\
            "\SED-SPEC-Dummy|Sed-Diam]]"

        _, hypermatches = find_hyperlinks(filter_wiki_text(text))

        exp_hypermatches = [('Storage of Data: ',
                             'file:',
                             '//\\en.tp.firm\\Diam$\\Com\\' +\
                             'SED_Dolore\\Magna-Aliquyam_PEDx' +\
                             '\x06%20lorem%20ipsum%20dolor%20sit' +\
                             '%20amet\x02%20labore%20magna\\P6\\' +\
                             'SED-Wizard\\SED-SPEC-Dummy',
                             '|Sed-Diam]]',
                             'Sed-Diam'),
                            '']

        self.assertEqual(
            hypermatches,
            exp_hypermatches,
            "hypermatches lists do not match!")
        # pylint: disable=anomalous-backslash-in-string
        text = "Storage of Data: [[file://\\en.tp.firm\Diam" +\
            "$\Com\SED_Dolore\Magna-Aliquyam_PEDx" +\
            "\006 lorem ipsum dolor sit amet" +\
            "\02 labore magna\P6\SED-Wizard" +\
            "\SED-SPEC-Dummy]]"

        _, hypermatches = find_hyperlinks(filter_wiki_text(text))

        exp_hypermatches = [('Storage of Data: ',
                             'file:',
                             '//\\en.tp.firm\\Diam$\\Com\\SED_Dolore' +\
                             '\\Magna-Aliquyam_PEDx\x06%20lorem%20' +\
                             'ipsum%20dolor%20sit%20amet\x02%20labore' +\
                             '%20magna\\P6\\SED-Wizard\\SED-SPEC-Dummy',
                             ']]',
                             ''),
                            '']

        self.assertEqual(
            hypermatches,
            exp_hypermatches,
            "hypermatches lists do not match!")

        text = "Storage of Data:[[" +\
            r"file:///\\lorem\diam$\Ipsum\PLM|Link" + "]]"

        _, hypermatches = find_hyperlinks(filter_wiki_text(text))

        exp_hypermatches = [('Storage of Data:',
                             'file:',
                             '///\\\\lorem\\diam$\\Ipsum\\PLM',
                             '|Link]]',
                             'Link'),
                            '']

        self.assertEqual(
            hypermatches,
            exp_hypermatches,
            "hypermatches lists do not match!")

    def test_find_hyperlinks_ii(self):
        """ Test find_hyperlinks."""

        text_list = ["wiki:SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_" +\
                     "EIRMOD_Elitr_Magna_5_Aliquyam_Erat",
                     "wiki:SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_" +\
                     "EIRMOD_Elitr_Magna_5_Aliquyam_Erat test",
                     "wiki:/SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_" +\
                     "EIRMOD_Elitr_Magna_5_Aliquyam_Erat",
                     "wiki:/SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_" +\
                     "EIRMOD_Elitr_Magna_5_Aliquyam_Erat test",
                     "http://www.test.com e:wiki/SED/" +\
                     "IPSUM-2017-Dolore-Magna/DIAM2/" +\
                     "Stet/SED_DIAM2_Stet_CL7_EIRMOD_" +\
                     "Elitr_Magna_5_Aliquyam_Erat ",
                     "[[e:wiki/SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_" +\
                     "EIRMOD_Elitr_Magna_5_Aliquyam_Erat]] test",
                     "[[e:wiki/SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_" +\
                     "Elitr_Magna_5_Aliquyam_Erat|Link1]] test",
                     "[e:wiki/SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_" +\
                     "Elitr_Magna_5_Aliquyam_Erat Link1] test",
                     "[http://www.test.com link1]," +\
                     " [e:wiki/SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_" +\
                     "Elitr_Magna_5_Aliquyam_Erat Link2] test",
                     "[[http://www.test.com|link1]]," +\
                     " [[e:wiki/SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_" +\
                     "Elitr_Magna_5_Aliquyam_Erat|Link2]] test",
                     "e:wiki/SED/IPSUM-2017-Dolore-Magna/" +\
                     "DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_" +\
                     "Elitr_Magna_5_Aliquyam_Erat",
                     "[[http://www.test.com]] test",
                     "r:#805 r:#806"]

        exp_hypermatches = [[('', 'wiki:', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat', '', '', ''),
                             ''],
                            [('', 'wiki:', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat', ' ', '', ' '),
                             'test'],
                            [('', 'wiki:', '/SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat', '', '', ''),
                             ''],
                            [('', 'wiki:', '/SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat', ' ', '', ' '),
                             'test'],
                            [('', 'http:', '//www.test.com', ' ', '', ' '),
                             ('', 'e:wiki/', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat', ' ', ' ', ''),
                             ''],
                            [('', 'e:wiki/', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat', ']]', ''),
                             ' test'],
                            [('', 'e:wiki/', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat',
                              '|Link1]]', 'Link1'), ' test'],
                            [('', 'e:wiki/', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat',
                              ' Link1]', 'Link1'), ' test'],
                            [('', 'http:', '//www.test.com',
                              ' link1]', 'link1'),
                             (', ', 'e:wiki/', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat',
                              ' Link2]', 'Link2'), ' test'],
                            [('', 'http:', '//www.test.com',
                              '|link1]]', 'link1'),
                             (', ', 'e:wiki/', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat',
                              '|Link2]]', 'Link2'), ' test'],
                            [('', 'e:wiki/', 'SED/IPSUM-2017-Dolore-Magna/' +\
                              'DIAM2/Stet/SED_DIAM2_Stet_CL7_EIRMOD_' +\
                              'Elitr_Magna_5_Aliquyam_Erat', '', '', ''), ''],
                            [('', 'http:', '//www.test.com',
                              ']]', ''), ' test'],
                            [('', 'r:#', '805', ' ', 'r:#805'),
                             ('', 'r:#', '806', '', 'r:#806'), '']]

        for i, text in enumerate(text_list):
            _, hypermatches = find_hyperlinks(text)
            self.assertEqual(exp_hypermatches[i],
                             hypermatches,
                             "Returned hypermatches list and expected " +\
                             "hypermatches list do not match!")

    def test_find_hyperlinks_iii(self):
        """ Test find_hyperlinks for
            regex_id == 4."""

        text = "[[Dummy-APO-Database/GPD/Material_Strength| MS-GPD]]"

        regex_id, hypermatches = find_hyperlinks(text)

        exp_hypermatches = [('',
                             'Dummy-APO-Database/',
                             'GPD/Material_Strength',
                             '| MS-GPD]]',
                             ' MS-GPD'),
                            '']

        exp_regex_id = 4

        self.assertEqual(
            hypermatches,
            exp_hypermatches,
            "list of hypermatches do not match!")

        self.assertEqual(
            regex_id,
            exp_regex_id,
            "Expected regex id does not match!")

    def test_get_storage_of_data(self):
        """ Test get_storage_of_data """

        easy_tasks = [
            (2, u'Summary 1', u'easy', u'reviewing', None, None,
             None, None, None, None, None, None,
             None, None, None, None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname|1|Link1]]'),
            (3, u'Summary 2', u'easy', u'reviewing', None, None,
             u'someone', None, None, None, None, None,
             None, None, None, None, None, u'bar',
             '[http://localhost/Coconut/event/wiki/Specname 2 Link2]'),
            (4, u'Summary 3', u'easy', u'reviewing', None, None,
             u'someone_else', None, None, None, None, None,
             None, None, None, None, None, u'baz',
             '[http://localhost/Coconut/event/wiki/Specname3 Link3]'),
            (5, u'Summary 4', u'easy', u'reviewing', None, None,
             u'none', u'bob', u'2008-08-01', None, None, None,
             None, None, None, None, None, None,
             '[[http://localhost/Coconut/event/wiki/Specname4|Link4]]')]

        storage_of_data = [[2,
                            u'Summary 1',
                            'Storage of Data: [[http://localhost/' +\
                            'Coconut/event/wiki/Specname|1|Link1 ' +\
                            '<- Please Check for pipe symbol or spaces]]'],
                           [3,
                            u'Summary 2',
                            'Storage of Data: [[http://localhost/' +\
                            'Coconut/event/wiki/Specname 2 Link2 ' +\
                            '<- Please Check for pipe symbol or spaces]]'],
                           [4,
                            u'Summary 3',
                            'Storage of Data: [[http://localhost/' +\
                            'Coconut/event/wiki/Specname3|Link3]]'],
                           [5,
                            u'Summary 4',
                            'Storage of Data: [[http://localhost/' +\
                            'Coconut/event/wiki/Specname4|Link4]]']]

        self.assertEqual(
            get_storage_of_data(easy_tasks),
            storage_of_data,
            "storage_of_data lists do not match!")

    def test_remove_forward_slash(self):
        """ Test remove_forward_slash """

        text = '/SED/IPSUM-2017-Dolore' +\
            '-Magna/DIAM2/Stet/SED_DIAM2_Stet_CL7_' +\
            'EIRMOD_Elitr_Magna_5_Aliquyam_Erat'

        exp_text = "SED/IPSUM-2017-Dolore-Magna/DIAM2/" +\
            "Stet/SED_DIAM2_Stet_CL7_EIRMOD_Elitr_Magna" +\
            "_5_Aliquyam_Erat"

        self.assertEqual(
            remove_forward_slash(text),
            exp_text,
            "exp_text lists do not match!")

        text = 'SED/IPSUM-2017-Dolore' +\
            '-Magna/DIAM2/Stet/SED_DIAM2_Stet_CL7_' +\
            'EIRMOD_Elitr_Magna_5_Aliquyam_Erat'

        self.assertEqual(
            remove_forward_slash(text),
            exp_text,
            "exp_text do not match!")

