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
    if self.transponder:
      if re.search(r'ES', self.transponder):
        return True
      elif self.transponder == 'GTX23':
        return True
      elif self.transponder == 'GTX345':
        return True
      else:
        return False
    else:
      return False

  def GetSanitizedModel(self):
    if self.title and self.model:
      if '201' in self.title or '201' in self.model:
        return '201'
      elif '231' in self.title or '231' in self.model:
        return '231'
      elif '252' in self.title or '252' in self.model:
        return '252'
      elif '305' in self.title or '305' in self.model:
        return '305'
      elif 'M20J' in self.title or 'M20J' in self.model:
        return '201'
      elif 'M20K' in self.title or 'M20K' in self.model:
        return '231'
      elif 'M20M' in self.title or 'M20M' in self.model:
        return 'BRAVO'
    else:
      return None

  def GetTbo(self):
    tbo = {'201': 2e3,
        '231': 1.8e3,
        '252': 1.8e3,
        '305': 1.6e3,
        'BRAVO': 1.8e3}

    model = self.GetSanitizedModel()
    if model:
      return tbo[model]
    else:
      return None

  def GetOverhaulCost(self):
    cost = {'201': 25e3,
        '231': 33e3,
        '252': 33e3,
        '305': 40e3,
        'BRAVO':50e3}

    model = self.GetSanitizedModel()
    if model:
      return cost[model]
    else:
      return None

  @property
  def adjusted_price(self):
    if self.price:
      adj_price = self.price
      if not self.HasWaasGps():
        adj_price += 17e3
      if not self.HasAdsbOut():
        adj_price += 5.5e3

      tbo = self.GetTbo()
      cost = self.GetOverhaulCost()
      if self.engine_hours and tbo and cost:
        adj_price += (self.engine_hours - tbo / 2) * cost / tbo
      return adj_price
