"""
This file demonstrates two different styles of tests (one doctest and one
unittest). These will both pass when you run "manage.py test".

Replace these with more appropriate tests for your application.
"""
import datetime
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Sum, Min, Max, Count
from django.utils import unittest
from django.test import TransactionTestCase as TestCase

from test_app import models

#-------------------------------------------------------------------------------
# Helper functions for quickly creating history records for models or instances
#-------------------------------------------------------------------------------
def create_history(model, prop, values, **initial_props):
    initial_props[prop] = values[0]
    instance = model.objects.create(**initial_props)
    add_history(instance, prop, values[1:])
    return instance

def add_history(instance, prop, values):
    for v in values:
        setattr(instance, prop, v)
        instance.save()

class BasicHistoryTest(TestCase):

    def setUp(self):
        self.model = getattr(self, 'model', models.VersionedModel)
        
        # account for the fact that the history manager won't always
        # be named 'history'
        self.history_manager = getattr(self, 'history_manager', 'history')

        # create ten history items
        self.obj = create_history(self.model, 'integer', range(10))

    def test_history_count(self):
        self.assertEqual(getattr(self.obj, self.history_manager).count(), 10)

    def test_in_filter_chain(self):
        # test counts by integer value - expect one each for the objects
        # we mocked, zero for values we didn't set
        expected = [(i, 1) for i in range(10)] + [(-1, 0), (10, 0)]

        for val, count in expected:
            filter = {'%s__integer' % self.history_manager: val}
            self.assertEqual(self.model.objects.filter(**filter).count(), count)

    def test_in_aggregates(self):
        aggcount = self.model.objects\
            .aggregate(x=Count(self.history_manager))['x']
        self.assertEqual(aggcount, 10)

        aggsum = self.model.objects\
            .aggregate(x=Sum('%s__integer' % self.history_manager))['x']
        self.assertEqual(aggsum, sum(range(10)))

    def test_primary_model_access(self):
        '''
        Test that HistoryManager and HistoryRecords (and its instances) have 
        access to the primary model that their history records shadow.
        '''
        m = create_history(self.model, 'integer', range(5))
        self.assertEqual(getattr(m, self.history_manager).primary_model, 
                         self.model)
        self.assertEqual(getattr(m, self.history_manager).all()[0].primary_model,
                         self.model)
        self.assertEqual(getattr(self.model, self.history_manager).primary_model,
                         self.model)

    def test_most_recent(self):
        # by instance
        m = create_history(self.model, 'characters', ['a', 'b', 'c'])
        m_most_recent = getattr(m, self.history_manager).most_recent()
        self.assertEqual(m_most_recent.characters, 'c')
        
        # by pk
        m_pk = m.pk
        m.delete()
        m_most_recent = getattr(self.model, self.history_manager)\
            .most_recent(pk=m_pk)
        self.assertEqual(m_most_recent.characters, 'c')

        
    def test_as_of(self):
        # set up tests
        before_create = datetime.datetime.now()        
        m = create_history(self.model, 'characters', ['a', 'b', 'c'])
        m_pk = m.pk
        after_create = datetime.datetime.now()
        
        # create a list of tuples of (lookup_date, expected_value) for exact
        # values of lookup_date, ordered from earliest to latest
        expected_vals = list(getattr(m, self.history_manager)\
                                 .order_by('history_date')\
                                 .values_list('history_date', 'characters'))
        last_mod, last_val = expected_vals[-1]
        expected_vals.append((after_create, last_val))
        
        # add (lookup_date, expected value) tuples for interpolated dates
        def interpolate_dates(date_min, date_max):
            return date_min + ((date_max - date_min) / 2)

        expected_vals += [(interpolate_dates(t1, t2), v1)
                          for ((t1, v1), (t2, v2)) in
                          zip(expected_vals[:-1], expected_vals[1:])]
        
        #-------------------------------
        # by instance
        #-------------------------------

        # lookup before item was created should fail
        with self.assertRaises(self.model.DoesNotExist):
            getattr(m, self.history_manager).as_of(before_create)

        # current lookup should match current history lookup
        self.assertEqual(m.characters, 
                         getattr(m, self.history_manager)\
                             .as_of(datetime.datetime.now())\
                             .characters)

        # exact and interpolated lookups should return their expected values
        for lookup_date, expected_value in expected_vals:
            self.assertEqual(expected_value,
                             getattr(m, self.history_manager)
                             .as_of(lookup_date).characters)

        #-------------------------------
        # by pk
        #-------------------------------

        # lookup before item was created should fail
        with self.assertRaises(self.model.DoesNotExist):
            getattr(self.model, self.history_manager)\
                .as_of(before_create, pk=m_pk)

        # lookup on bogus pk should fail
        with self.assertRaises(self.model.DoesNotExist):
            getattr(self.model, self.history_manager)\
                .as_of(datetime.datetime.now(), pk=10000) # fake pk

        # exact and interpolated lookups should return their expected values,
        # even after deletion of the primary object
        m.delete()
        for lookup_date, expected_value in expected_vals:
            hist_obj = getattr(self.model, self.history_manager)\
                .as_of(lookup_date, pk=m_pk)
            self.assertEqual(expected_value, hist_obj.characters)

    def test_get_or_restore(self):
        m = create_history(self.model, 'integer', range(3))
        m_pk = m.pk

        # now you see it...
        m2 = getattr(self.model, self.history_manager).get_or_restore(pk=m_pk)
        self.assertEqual(m.integer, m2.integer)
        self.assertEqual(m_pk, m2.pk)

        # ...now you don't...
        m.delete()
        with self.assertRaises(self.model.DoesNotExist):
            self.model.objects.get(pk=m_pk)

        # ...now you do again!
        m3 = getattr(self.model, self.history_manager).get_or_restore(pk=m_pk)
        self.assertEqual(m.integer, m3.integer)
        self.assertEqual(m_pk, m3.pk)
        m3.save()

        m4 = self.model.objects.get(pk=m_pk)
        self.assertEqual(m.integer, m4.integer)
        self.assertEqual(m_pk, m4.pk)

    def test_editors(self):
        users = [User.objects.create_user(u, '%s@example.com' % u, u)
                 for u in ['alan', 'beth', 'chet', 'dora']]
        m = self.model()
        for idx, val in enumerate(range(12)):
            m.integer = val
            m.save(editor=users[idx % len(users)])

        for u in users:
            self.assertEqual(getattr(m, self.history_manager)\
                                 .filter(history_editor=u).count(), 3)

        for idx, hrec in enumerate(getattr(m, self.history_manager)\
                                       .all().order_by('history_id')):
            self.assertEqual(hrec.history_editor, users[idx % len(users)])

@unittest.skip("Inherited classes aren't supported yet")
class InheritedFkTest(BasicHistoryTest):
    def setUp(self):
        self.model = models.InheritedVersionedModel
        super(InheritedFkTest, self).setUp()

class AlternatePkNameTest(BasicHistoryTest):
    def setUp(self):
        self.model = models.AlternatePkNameModel
        super(AlternatePkNameTest, self).setUp()

class RenamedHistoryFieldTest(BasicHistoryTest):
    def setUp(self):
        self.model = models.RenamedHistoryFieldModel
        self.history_manager = 'othername'
        super(RenamedHistoryFieldTest, self).setUp()

class FkTestCase(TestCase):
    def setUp(self):
        self.nv = models.NonversionedModel.objects\
            .create(characters='nonversioned')

        self.v = create_history(models.VersionedModel,
                                'characters',
                                ['version%s' % x for x in range(10)])

class PreservedForeignKeyTest(FkTestCase):

    def setUp(self):
        super(PreservedForeignKeyTest, self).setUp()
        nv_rel = create_history(models.PreserveFkToNonversionedModel,
                                'characters',
                                ['preserved_nv_%s' % x  for x in range(10)],
                                fk=self.nv)

        v_rel = create_history(models.PreserveFkToVersionedModel,
                              'characters',
                              ['preserved_v_%s' % x  for x in range(10)],
                              fk=self.v)

    def test_related_reference(self):
        '''
        Assert that the preserved foreign key fields are available by reference
        bidirectionally:
        - One related primary item
        - Ten historical items available through {related_name}_historical
        - All historical items reference related items through a real foreign
          key
        '''
        for p in [self.nv, self.v]:
            self.assertEqual(p.rel_p.count(), 1)
            self.assertEqual(p.rel_p_historical.count(), 10)
            self.assertEqual(p.rel_p_historical.exclude(fk=p).count(), 0)

    def test_drop_parent_cascade(self):
        self.nv.delete()
        self.assertEqual(models.PreserveFkToNonversionedModel.objects.count(), 0)
        self.assertEqual(models.PreserveFkToNonversionedModel.history.count(), 0)

        self.v.delete()
        self.assertEqual(models.PreserveFkToVersionedModel.objects.count(), 0)
        self.assertEqual(models.PreserveFkToVersionedModel.history.count(), 0)


class ConvertedForeignKeyTest(FkTestCase):

    def setUp(self):
        super(ConvertedForeignKeyTest, self).setUp()
        nv_rel = create_history(models.ConvertFkToNonversionedModel,
                                'characters',
                                ['converted_nv_%s' % x  for x in range(10)],
                                fk=self.nv)

        v_rel = create_history(models.ConvertFkToVersionedModel,
                              'characters',
                              ['converted_v_%s' % x  for x in range(10)],
                              fk=self.v)

    def test_drop_parent_cascade(self):
        ''' Primary objects should be removed, but history should still exist '''
        self.nv.delete()
        self.assertEqual(models.ConvertFkToNonversionedModel.objects.count(), 0)
        self.assertNotEqual(models.ConvertFkToNonversionedModel.history.count(), 0)
        self.v.delete()
        self.assertEqual(models.ConvertFkToVersionedModel.objects.count(), 0)
        self.assertNotEqual(models.ConvertFkToVersionedModel.history.count(), 0)

class PropertyPatchTest(TestCase):
    def test_properties(self):
        # create model with multiple versions and assert that 'created_date'
        # and 'last_modified_date' are accessible and not equal
        m = create_history(models.MonkeyPatchedPropertiesTestModel, 
                           'integer', range(5))
        self.assertNotEqual(m.created_date, m.last_modified_date)

class OnDeleteTest(TestCase):
    def test_on_delete_set_null(self):
        n = models.NonversionedModel.objects.create(characters='nonversioned')
        m = create_history(models.NullCascadingFkModel,
                           'integer', range(5),
                           fk=n)

        # delete fk relation and ensure that object and its history remain
        n.delete()
        m = m.__class__.objects.get(id=m.id)
        self.assertEqual(m.fk, None)
        self.assertEqual(m.history.count(), 5)
        for mh in m.history.all():
            self.assertEqual(m.fk, None)


class DateFieldAutoNowTest(TestCase):
    def test_auto_now_fields(self):
        '''
        Ensure that date and time fields are properly converted so that auto_now
        and auto_now_add don't produce unexpected results in history.
        '''
        m = create_history(models.DateFieldTestModel, 'integer', range(5))
        for field_type in ['date', 'time', 'datetime']:

            # the primary item should match the latest historical record on
            # values in auto_now fields
            field_name = 'auto_now_%s' % field_type
            latest = getattr(m, field_name)
            latest_historical = m.history.aggregate(x=Max(field_name))['x']
            self.assertEqual(latest, latest_historical)

            # all other versions should be earlier (except in the case of
            # 'date', where they will be earlier or equal due to its resolution)
            if field_type == 'date':
                lte_versions = m.history.filter(**{'%s__lte' % field_name:
                                                       latest_historical})
                self.assertEqual(lte_versions.count(), 5)
            else:
                lt_versions = m.history.filter(**{'%s__lt' % field_name:
                                                      latest_historical})
                self.assertEqual(lt_versions.count(), 4)

            # the primary item should retain the same date as the first 
            # historical record for auto_now_add fields
            field_name = 'auto_now_add_%s' % field_type
            earliest = getattr(m, field_name)
            earliest_historical = m.history.aggregate(x=Min(field_name))['x']
            self.assertEqual(earliest, earliest_historical)

            # all subsequent versions should have an identical date
            equal_versions = m.history.filter(**{field_name: 
                                                 earliest_historical})
            self.assertEqual(equal_versions.count(), 5)
