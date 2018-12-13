from __future__ import unicode_literals
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils import timezone
import threading


class ActiveMixinManager(models.Manager):
    """Manager class for ActiveMixin.
    """
    def current(self):
        return self.filter(effective_to=None)

    def deleted(self):
        return self.filter(effective_to__isnull=False)


class ActiveMixin(models.Model):
    """Model mixin to allow objects to be saved as 'non-current' or 'inactive',
    instead of deleting those objects.
    The standard model delete() method is overridden.

    "effective_to" is used to flag 'deleted' objects (not null==deleted).
    """
    effective_to = models.DateTimeField(null=True, blank=True)
    objects = ActiveMixinManager()

    class Meta:
        abstract = True

    def is_active(self):
        return self.effective_to is None

    def is_deleted(self):
        return not self.is_active()

    def delete(self, *args, **kwargs):
        """Overide the standard delete method; sets effective_to the current
        date and time.
        """
        if 'force' in kwargs and kwargs['force']:
            kwargs.pop('force', None)
            super(ActiveMixin, self).delete(*args, **kwargs)
        else:
            self.effective_to = timezone.now()
            super(ActiveMixin, self).save(*args, **kwargs)


class AuditMixin(models.Model):
    """Model mixin to update creation/modification datestamp and user
    automatically on save.
    """
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.PROTECT,
        related_name='%(app_label)s_%(class)s_created', editable=False)
    modifier = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.PROTECT,
        related_name='%(app_label)s_%(class)s_modified', editable=False)
    created = models.DateTimeField(default=timezone.now, editable=False)
    modified = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(AuditMixin, self).__init__(*args, **kwargs)
        self._initial = {}
        if self.pk:
            for field in self._meta.fields:
                self._initial[field.attname] = getattr(self, field.attname)

    def has_changed(self):
        """Returns True if the current data object differs from saved.
        """
        return bool(self.changed_data)

    @property
    def changed_data(self):
        """Returns a list of fields with data that differs from initial
        values. May be utilised by revision mechanisms, as required.
        """
        self._changed_data = []
        for field, value in self._initial.items():
            if field in ["modified", "modifier_id"]:
                continue  # Disregard modifer field as a test for changed data.
            if getattr(self, field) != value:
                self._changed_data.append(field)
        return self._changed_data
