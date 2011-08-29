from django.db import models
from history.models import HistoricalRecords, CONVERT, PRESERVE

class BaseModel(models.Model):
    '''
    Abstract model that contributes a set of standard fields to the test models
    so we don't have to repeatedly make up or copy fields that we don't actually
    care about.
    '''
    characters = models.CharField(max_length=255, blank=True)
    integer = models.IntegerField(default=-1)
    boolean = models.BooleanField(default=True)
    
    class Meta:
        abstract = True

class NonversionedModel(BaseModel):
    pass
    
class VersionedModel(BaseModel):
    history = HistoricalRecords()

class InheritedVersionedModel(VersionedModel):
    '''
    Test that history fields are correctly inherited.
    '''
    pass

class RenamedHistoryFieldModel(BaseModel):
    '''
    Test that the magic still works when this field has a name other than
    'history' (i.e. ensure that the name 'history' is not hard-coded in the
    HistoricalRecords handling).
    '''
    othername = HistoricalRecords()

class MonkeyPatchedPropertiesTestModel(BaseModel):
    '''
    Test the monkey-patching of 'created_date' and 'last_modified_date'
    properties onto this model.
    '''
    history = HistoricalRecords(add_history_properties=True)

class PreserveFkToNonversionedModel(BaseModel):
    '''
    Model with a foreign key to our non-versioned model with history records 
    that preserve a real foreign key to that model.
    '''
    fk = models.ForeignKey('NonversionedModel', related_name='rel_p')
    history = HistoricalRecords(key_conversions={'fk': PRESERVE})

class PreserveFkToVersionedModel(BaseModel):
    fk = models.ForeignKey('VersionedModel', related_name='rel_p')
    history = HistoricalRecords(key_conversions={'fk': PRESERVE})

class ConvertFkToNonversionedModel(BaseModel):
    '''
    Model with a foreign key to our non-versioned model with history records 
    that convert the foreign key to a non-foreign key field mirroring the 
    referenced model's primary key (typically an IntegerField).
    '''
    fk = models.ForeignKey('NonversionedModel', related_name='rel_c')
    history = HistoricalRecords(key_conversions={'fk': CONVERT})

class ConvertFkToVersionedModel(BaseModel):
    fk = models.ForeignKey('VersionedModel', related_name='rel_c')
    history = HistoricalRecords(key_conversions={'fk': CONVERT})

class DateFieldTestModel(BaseModel):
    '''
    Test model to ensure that date and time fields are properly copied to 
    history records, and that 'auto_now' and 'auto_now_add' behaviors are 
    removed.
    '''
    history = HistoricalRecords()

    auto_now_date = models.DateField(auto_now=True)
    auto_now_add_date = models.DateField(auto_now_add=True)

    auto_now_time = models.TimeField(auto_now=True)
    auto_now_add_time = models.TimeField(auto_now_add=True)

    auto_now_datetime = models.DateTimeField(auto_now=True)
    auto_now_add_datetime = models.DateTimeField(auto_now_add=True)

#-------------------------------------------------------------------------------
# Test models for abstract foreign key bases
# (see https://docs.djangoproject.com/en/dev/topics/db/models/#abstract-related-name)
#
# Test failures for this should manifest themselves at model validation time.
#-------------------------------------------------------------------------------
class AbstractFkBaseModel(BaseModel):
    fk = models.ForeignKey('NonversionedModel', 
                           related_name='%(app_label)s_%(class)s_related')
    class Meta(BaseModel.Meta):
        abstract=True

class ConcretizedAbstractFkModel1(AbstractFkBaseModel):
    history = HistoricalRecords(key_conversions={'fk': CONVERT})

class ConcretizedAbstractFkModel2(AbstractFkBaseModel):
    history = HistoricalRecords(key_conversions={'fk': CONVERT})


class DeferredClassBuildModel(BaseModel):
    '''
    Model to test that foreign keys can be specified in any order and that 
    historical record creation still functions as expected.

    Test failures for this class should manifest themselves at model validation
    time.
    '''
    fk1 = models.ForeignKey('NonversionedModel')
    history = HistoricalRecords()
    fk2 = models.ForeignKey('VersionedModel')
    
    
    
