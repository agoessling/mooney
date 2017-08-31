import peewee
import re
from wtfpeewee.orm import model_form

db = peewee.SqliteDatabase('mooney.db', check_same_thread=False)

class Listing(peewee.Model):
  title = peewee.CharField()
  url = peewee.CharField(unique=True)
  year = peewee.IntegerField(null=True)
  model = peewee.CharField(null=True)
  registration = peewee.CharField(null=True)
  serial = peewee.CharField(null=True)
  airframe_hours = peewee.FloatField(null=True)
  engine_hours = peewee.FloatField(null=True)
  overhaul_type = peewee.CharField(null=True)
  gps = peewee.CharField(null=True)
  transponder = peewee.CharField(null=True)
  city = peewee.CharField(null=True)
  state = peewee.CharField(null=True)
  price = peewee.FloatField(null=True)
  source_time = peewee.TimestampField()
  sold = peewee.BooleanField(null=False, default=False)
  starred = peewee.BooleanField(null=False, default=False)
  eliminated = peewee.BooleanField(null=False, default=False)
  notes = peewee.TextField(null=True)

  class Meta:
    database = db

  def HasWaasGps(self):
    return self.gps in ['GTN650', 'GTN750', 'GNS530W', 'GNS430W']

  def HasAdsbOut(self):
    if re.search(r'ES', self.transponder):
      return True
    elif self.transponder == 'GTX23':
      return True
    else:
      return False
