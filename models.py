import peewee
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

  class Meta:
    database = db

ListingForm = model_form(Listing, exclude=['title', 'url', 'source_time'])
