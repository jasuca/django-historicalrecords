"""
This file demonstrates two different styles of tests (one doctest and one
unittest). These will both pass when you run "manage.py test".

Replace these with more appropriate tests for your application.
"""

from django.db.models import Sum, Min, Max, Count
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
        # create ten history items
        self.obj = create_history(models.VersionedModel, 'integer', range(10))

    def test_history_count(self):
        self.assertEqual(self.obj.history.count(), 10)

    def test_in_filter_chain(self):
        self.assertEqual(models.VersionedModel.objects\
                             .filter(history__integer=-1).count(), 0)
        self.assertEqual(models.VersionedModel.objects\
                             .filter(history__integer=10).count(), 0)
        for i in range(10):
            self.assertEqual(models.VersionedModel.objects\
                                 .filter(history__integer=i).count(), 1)

    def test_in_aggregates(self):
        aggcount = models.VersionedModel.objects\
            .aggregate(x=Count('history'))['x']
        self.assertEqual(aggcount, 10)

        aggsum = models.VersionedModel.objects\
            .aggregate(x=Sum('history__integer'))['x']
        self.assertEqual(aggsum, sum(range(10)))


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
        m = models.MonkeyPatchedPropertiesTestModel.objects.create(integer=1)
        m.integer = 2
        m.save()
        m.integer = 3
        m.save()
        self.assertNotEqual(m.created_date, m.last_modified_date)

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
            

