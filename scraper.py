#!/usr/bin/python3

import argparse
import bs4
import logging
from models import Listing
import peewee
import re
from state_abbrev import state_abbrev
import smtplib
import time
import urllib.parse
import urllib.request

_HEADERS = {'User-Agent': 'Mozilla/5.0'}
_REQ_DELAY = 0.5
_EMAIL_RECIPIENTS = ['agoessling@gmail.com', 'andrew.goessling@kittyhawk.aero']

_CONTROLLER_URLS = [
    'https://www.controller.com/listings/aircraft/for-sale/list/category/13/' +
    'aircraft/manufacturer/mooney/model/m20m-bravo',
    'https://www.controller.com/listings/aircraft/for-sale/list/category/13/' +
    'aircraft/manufacturer/mooney/model-group/m20k',
    'https://www.controller.com/listings/aircraft/for-sale/list/category/13/' +
    'aircraft/manufacturer/mooney/model-group/m20j'
]
_TRADE_A_PLANE_URLS = [
    'https://www.trade-a-plane.com/search?s-page_size=100&category_level1=' +
    'Single+Engine+Piston&make=MOONEY&model=M20J+201&s-type=aircraft',
    'https://www.trade-a-plane.com/search?s-page_size=100&category_level1=' +
    'Single+Engine+Piston&make=MOONEY&model=M20J+205&s-type=aircraft',
    'https://www.trade-a-plane.com/search?s-page_size=100&category_level1=' +
    'Single+Engine+Piston&make=MOONEY&model=M20K+231&s-type=aircraft',
    'https://www.trade-a-plane.com/search?s-page_size=100&category_level1=' +
    'Single+Engine+Piston&make=MOONEY&model=M20K+252&s-type=aircraft',
    'https://www.trade-a-plane.com/search?s-page_size=100&category_level1=' +
    'Single+Engine+Piston&make=MOONEY&model=M20K+305+ROCKET&s-type=aircraft',
    'https://www.trade-a-plane.com/search?s-page_size=100&category_level1=' +
    'Single+Engine+Piston&make=MOONEY&model=M20M+BRAVO&s-type=aircraft',
    'https://www.trade-a-plane.com/search?s-page_size=100&category_level1=' +
    'Single+Engine+Piston&make=MOONEY&model=M20M+TLS+BRAVO&s-type=aircraft'
]

def SendEmail(subject, body):
  session = smtplib.SMTP('smtp.gmail.com', 587)
  session.ehlo()
  session.starttls()
  session.ehlo()
  session.login('agoessling@gmail.com', 'yedvoxtyqrbludsf')
  
  headers = '\r\n'.join([
      'From: Mooney Scraper',
      'Subject: ' + subject,
      'To: ' + ', '.join(_EMAIL_RECIPIENTS),
      'MIME-Version: 1.0',
      'Content-Type: text/html'])

  session.sendmail('agoessling@gmail.com', _EMAIL_RECIPIENTS, headers + '\r\n\r\n' + body)

def FindGps(html):
  gps_match = re.search(r'(?:GTN|GNS|KLN)[\s-]*'
      + r'(?:650|750|430|530|89|94)[\s-]*W?',
      html, flags=re.IGNORECASE)
  if gps_match:
    gps = re.sub(r'[\s-]', '', gps_match.group().upper())
    waas_match = re.search(r'WAAS', html, flags=re.IGNORECASE)
    if waas_match and not 'GTN' in gps and not gps[-1] == 'W':
      gps += 'W'
    return gps
  else:
    return None

def FindTransponder(html):
  transponder_match = re.search(r'(?:GTX|KT)[\s-]*\d{2,5}[A-Z]*', html,
      flags=re.IGNORECASE)
  if transponder_match:
    return re.sub(r'[\s-]', '', transponder_match.group().upper())
  else:
    return None

def SanitizeState(state_string):
  if state_string:
    if state_string.title() in state_abbrev:
      return state_abbrev[state_string.title()]
    else:
      return state_string
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
    val_str = re.sub(r'[^(0-9\.)]', '', soup)
    if val_str:
      return convert_func(val_str)
    else:
      return None
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
  if not re.search(r'\d', listing.registration):
    listing.registration = None
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
      listing.state = SanitizeState(location_strs[0].split(' ')[0]\
          .replace('\n', ''))
    elif len(location_strs) == 2:
      listing.city = location_strs[0]
      listing.state = SanitizeState(location_strs[1].strip().split(' ')[0]\
          .replace('\n', ''))

  listing.gps = FindGps(html)
  listing.transponder = FindTransponder(html)

  return listing

def ParseTradeAPlaneSummary(url):
  logger.info('Scraping Trade-A-Plane summary: {}'.format(url))

  load_time = time.time()

  request = urllib.request.Request(url, headers=_HEADERS)
  soup = bs4.BeautifulSoup(urllib.request.urlopen(request), 'lxml')

  result_divs = soup.find_all('div', class_='result')

  logger.info('Found {:d} Trade-A-Plane listings.'.format(len(result_divs)))

  new_listings = []

  for div in result_divs:
    while time.time() < load_time + _REQ_DELAY:
      time.sleep(0.1)

    listing_url = urllib.parse.urljoin(url, div.a['href'])
    try:
      Listing.get(Listing.url == listing_url)
      logger.info('Skipping {}.'.format(div.a.next_element.strip()))
      continue
    except peewee.DoesNotExist:
      logger.info('Opening {}.'.format(div.a.next_element.strip()))

    load_time = time.time()

    try:
      listing = ParseTradeAPlaneListing(listing_url)
    except KeyboardInterrupt:
      raise
    except:
      logger.exception('Error parsing Trade-A-Plane listing: {}'.format(url))
      continue

    if listing.registration:
      try:
        Listing.get(Listing.registration == listing.registration)
        logger.info('Duplicate Registration {}: {}.'.format(
            listing.registration,
            div.a.next_element.strip()))
        continue
      except peewee.DoesNotExist:
        pass

    listing.save()
    new_listings.append(listing)

  return new_listings

def FindControllerSpec(soup, spec_name, convert_func=None):
  name_div = soup.find('div', class_='spec-name', string=spec_name)
  if name_div:
    sibling = name_div.find_next_sibling('div')
    if sibling:
      if convert_func:
        if convert_func == float or convert_func == int:
          val_str = re.sub(r'[^(0-9\.)]', '', sibling.string)
          if val_str:
            return convert_func(val_str)
        else:
          return convert_func(sibling.string)
      else:
        return sibling.string
  return None

def ParseControllerListing(url):
  request = urllib.request.Request(url, headers=_HEADERS)
  html = urllib.request.urlopen(request).read().decode('utf-8')
  soup = bs4.BeautifulSoup(html, 'lxml')
  listing = Listing()

  listing.title = soup.find('h1').string.strip()
  listing.url = url

  h4s = soup.find_all('h4')
  for h4 in h4s:
    if h4.find(text=re.compile(r'For Sale Price:')):
      price_str = re.sub(r'[^(\d\.)]', '', h4.next_element)
      if price_str:
        listing.price = float(price_str)
      break

  listing.year = FindControllerSpec(soup, 'Year', int)
  listing.registration = FindControllerSpec(soup, 'Registration #')
  if not re.search(r'\d', listing.registration):
    listing.registration = None
  listing.model = FindControllerSpec(soup, 'Model')
  listing.serial = FindControllerSpec(soup, 'Serial #')
  listing.airframe_hours = FindControllerSpec(soup, 'Total Time', float)

  overhaul_str = FindControllerSpec(soup, 'Overhaul')
  if overhaul_str:
    hours_match = re.search(r'([0-9,\.]+)', overhaul_str)
    type_match = re.search(r'(?:[0-9,\.]+)\s*([a-zA-Z]+)', overhaul_str)
    if hours_match:
      listing.engine_hours = float(hours_match.group(1).replace(',',''))
    if type_match:
      listing.overhaul_type = type_match.group(1)

  location = soup.find('a', class_='machinelocation').string
  if location and location.string:
    location_strs = location.string.split(',')
    if len(location_strs) == 1:
      listing.state = SanitizeState(location_strs[0])
    elif len(location_strs) == 2:
      listing.city = location_strs[0]
      listing.state = SanitizeState(location_strs[1].strip())

  listing.gps = FindGps(html)
  listing.transponder = FindTransponder(html)

  return listing

def ParseControllerSummary(url, page=1):
  logger.info('Scraping Controller Summary, Page {:d}: {}'.format(page, url))

  load_time = time.time()

  request = urllib.request.Request(url, headers=_HEADERS)
  soup = bs4.BeautifulSoup(urllib.request.urlopen(request), 'lxml')
  name_divs = soup.find_all('div', class_='listing-name')

  logger.info('Found {:d} Controller listings.'.format(len(name_divs)))

  new_listings = []

  for div in name_divs:
    while time.time() < load_time + _REQ_DELAY:
      time.sleep(0.1)

    listing_url = urllib.parse.urljoin(url, div.a['href'])
    try:
      Listing.get(Listing.url == listing_url)
      logger.info('Skipping {}.'.format(div.a.next_element.strip()))
      continue
    except peewee.DoesNotExist:
      logger.info('Opening {}.'.format(div.a.next_element.strip()))

    load_time = time.time()

    try:
      listing = ParseControllerListing(listing_url)
    except KeyboardInterrupt:
      raise
    except:
      logger.exception('Error parsing Controller listing: {}'.format(url))
      continue

    if listing.registration:
      try:
        Listing.get(Listing.registration == listing.registration)
        logger.info('Duplicate Registration {}: {}.'.format(
            listing.registration,
            div.a.next_element.strip()))
        continue
      except peewee.DoesNotExist:
        pass

    listing.save()
    new_listings.append(listing)

  next_btn = soup.select('a.btn.next')
  if next_btn:
    next_page_url = urllib.parse.urljoin(url, next_btn[0]['href'])
    new_listings += ParseControllerSummary(next_page_url, page + 1)

  return new_listings

if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description='Scrapes web for aircraft sales listings.')
  parser.add_argument('--log-file',
      help='Path to log file.  Defaults to stdout.')
  parser.add_argument('--verbose', action='store_true',
      help='Verbose logging information.')
  args = parser.parse_args()

  logger = logging.getLogger('Scraper')

  if args.verbose:
    level = logging.DEBUG
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
  else:
    level = logging.INFO
    formatter = logging.Formatter('[%(levelname)s] %(message)s')

  if args.log_file:
    handler = logging.FileHandler(args.log_file)
    handler.setFormatter(formatter)
  else:
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

  logger.propagate = False
  logger.setLevel(level)
  logger.addHandler(handler)

  Listing.create_table(fail_silently=True)

  logging.info('Starting scrape.')

  new_listings = []

  for url in _CONTROLLER_URLS:
    try:
      new_listings += ParseControllerSummary(url)
    except KeyboardInterrupt:
      raise
    except:
      logging.exception('Error parsing Controller summary: {}'.format(url))
      continue

  for url in _TRADE_A_PLANE_URLS:
    try:
      new_listings += ParseTradeAPlaneSummary(url)
    except KeyboardInterrupt:
      raise
    except:
      logging.exception('Error parsing Trade-A-Plane summary: {}'.format(url))
      continue

  logger.info('Found {:d} new listings.'.format(len(new_listings)))
