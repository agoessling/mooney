#!/usr/bin/python3

import bs4
import peewee
import pprint
import re
import time
import urllib

pp = pprint.PrettyPrinter(indent=2)

db = peewee.SqliteDatabase('mooney.db')

_HEADERS = {'User-Agent': 'Mozilla/5.0'}
_REQ_DELAY = 0.5
controller_url = 'https://www.controller.com/listings/aircraft/for-sale/list/category/13/aircraft/manufacturer/mooney/model-group/m20j'
trade_url = 'https://www.trade-a-plane.com/search?make=MOONEY&model_group=MOONEY+M20+SERIES&s-type=aircraft'

class Listing(peewee.Model):
  title = peewee.CharField()
  url = peewee.CharField(unique=True)
  price = peewee.FloatField()
  year = peewee.IntegerField()
  registration = peewee.CharField()
  model = peewee.CharField()
  serial = peewee.CharField()
  engine_hours = peewee.FloatField(null=True)
  overhaul_type = peewee.CharField(null=True)
  airframe_hours = peewee.FloatField()
  gps = peewee.CharField(null=True)
  transponder = peewee.CharField(null=True)
  state = peewee.CharField()
  city = peewee.CharField(null=True)
  source_time = peewee.TimestampField()

  class Meta:
    database = db

  def __repr__(self):
    return pprint.pformat(self._data)

def FindGps(html):
  gps_match = re.search(r'(?:GTN|GNS|KLN)[\s-]*'
      + r'(?:650|750|430|530|89|94)[\s-]*W?',
      html, flags=re.IGNORECASE)
  if gps_match:
    gps = re.sub('[\s-]', '', gps_match.group().upper())
    waas_match = re.search(r'WAAS', html, flags=re.IGNORECASE)
    if waas_match and not gps[-1] == 'W':
      gps += 'W'
    return gps
  else:
    return None

def FindTransponder(html):
  transponder_match = re.search(r'(?:GTX|KT)[\s-]*\d{2,}[A-Z]*', html,
      flags=re.IGNORECASE)
  if transponder_match:
    return re.sub('[\s-]', '', transponder_match.group().upper())
  else:
    return None

def FindTradeAPlaneSpec(soup, prop_name=None, convert_func=None):
  if not soup:
    return None

  if prop_name == 'string':
    soup = soup.string.strip()
  elif prop_name == 'next_sibling':
    soup = soup.next_sibling.strip()

  if not soup:
    return None

  if convert_func == float or convert_func == int:
    return convert_func(soup.replace(',', ''))
  elif convert_func:
    return convert_func(soup)
  else:
    return soup

def ParseTradeAPlaneListing(url):
  request = urllib.request.Request(url, headers=_HEADERS)
  html = urllib.request.urlopen(request).read().decode('utf-8')
  soup = bs4.BeautifulSoup(html, 'lxml')
  listing = Listing()

  listing.title = FindTradeAPlaneSpec(soup.find('h1'), 'string')
  listing.url = url
  listing.price = FindTradeAPlaneSpec(soup.find('span', itemprop='price'),
      'string', float)
  listing.year = FindTradeAPlaneSpec(soup.find('label', string='Year:'),
      'next_sibling', int)
  listing.registration = FindTradeAPlaneSpec(soup.find('label',
        string='Registration #:'), 'next_sibling')
  listing.model = FindTradeAPlaneSpec(soup.find('span',
        itemprop='manufacturer'), 'next_sibling')
  listing.serial = FindTradeAPlaneSpec(soup.find('label',
        string='Serial #:'), 'next_sibling')
  listing.airframe_hours = FindTradeAPlaneSpec(soup.find('label',
        string='Total Time:'), 'next_sibling', float)

  overhaul_str = FindTradeAPlaneSpec(soup.find('label',
        string='Engine 1 Overhaul Time:'), 'next_sibling')
  if overhaul_str:
    overhaul_strs = overhaul_str.split(' ')
    if len(overhaul_strs) > 0:
      listing.engine_hours = float(overhaul_strs[0].replace(',', ''))
    if len(overhaul_strs) > 1:
      listing.overhaul_type = overhaul_strs[1]

  location_str = FindTradeAPlaneSpec(soup.find('label', string='Location:'),
      'next_sibling')
  if location_str:
    location_strs = location_str.split(',')
    if len(location_strs) == 1:
      listing.state = location_strs[0].split(' ')[0].replace('\n','')
    elif len(location_strs) == 2:
      listing.city = location_strs[0]
      listing.state = location_strs[1].strip().split(' ')[0].replace('\n','')

  listing.gps = FindGps(html)
  listing.transponder = FindTransponder(html)

  return listing

def ParseTradeAPlaneSummary(url):
  load_time = time.time()

  request = urllib.request.Request(url, headers=_HEADERS)
  soup = bs4.BeautifulSoup(urllib.request.urlopen(request), 'lxml')

  result_divs = soup.find_all('div', class_='result')

  print('Found {:d} listings.'.format(len(result_divs)))

  listings = []

  for div in result_divs:
    while time.time() < load_time + _REQ_DELAY:
      time.sleep(0.1)

    print('Opening {}.'.format(div.a.text.strip()))
    listing_url = urllib.parse.urljoin(url, div.a['href'])
    load_time = time.time()
    listing = ParseTradeAPlaneListing(listing_url)
    pp.pprint(listing)
    listings.append(listing)

  return listings


def ParseControllerSummary(url):
  load_time = time.time()

  request = urllib.request.Request(url, headers=_HEADERS)
  soup = bs4.BeautifulSoup(urllib.request.urlopen(request), 'lxml')
  name_divs = soup.find_all('div', class_='listing-name')

  print('Found {:d} listings.'.format(len(name_divs)))

  for div in name_divs:
    while time.time() < load_time + _REQ_DELAY:
      time.sleep(0.1)

    listing_url = urllib.parse.urljoin(url, div.a['href'])
    try:
      Listing.get(Listing.url == listing_url)
      continue
    except peewee.DoesNotExist:
      pass

    print('Opening {}.'.format(div.a.string))
    load_time = time.time()
    listing = ParseControllerListing(listing_url)
    listing.save()

def ParseControllerListing(url):
  request = urllib.request.Request(url, headers=_HEADERS)
  html = urllib.request.urlopen(request).read().decode('utf-8')
  soup = bs4.BeautifulSoup(html, 'lxml')
  listing = Listing()

  listing.title = soup.find('h1').string.strip()
  listing.url = url
  price_str = soup.find('h4', string=re.compile('For Sale Price:')).string
  if price_str:
    listing.price = re.sub(r'[^(\d\.)]', '', price_str)
  listing.year = FindControllerSpec(soup, 'Year', int)
  listing.registration = FindControllerSpec(soup, 'Registration #')
  listing.model = FindControllerSpec(soup, 'Model')
  listing.serial = FindControllerSpec(soup, 'Serial #')
  listing.airframe_hours = FindControllerSpec(soup, 'Total Time', float)

  overhaul_str = FindControllerSpec(soup, 'Overhaul')
  if overhaul_str:
    listing.engine_hours = float(overhaul_str.split(' ')[0].replace(',', ''))
    listing.overhaul_type = overhaul_str.split(' ')[1]

  location = soup.find('a', class_='machinelocation').string
  if location and location.string:
    location_strs = location.string.split(',')
    if len(location_strs) == 1:
      listing.state = location_strs[0]
    elif len(location_strs) == 2:
      listing.city = location_strs[0]
      listing.state = location_strs[1].strip()

  listing.gps = FindGps(html)
  listing.transponder = FindTransponder(html)

  return listing

def FindControllerSpec(soup, spec_name, convert_func=None):
  name_div = soup.find('div', class_='spec-name', string=spec_name)
  if name_div:
    sibling = name_div.find_next_sibling('div')
    if sibling:
      if convert_func:
        if convert_func == float:
          return convert_func(sibling.string.replace(',', ''))
        else:
          return convert_func(sibling.string)
      else:
        return sibling.string
  return None

if __name__ == '__main__':
  db.connect()
  Listing.create_table(fail_silently=True)
  ParseControllerSummary(controller_url)
