#!/usr/bin/python3

import argparse
import bs4
import functools
import logging
from models import Listing
import peewee
import re
from state_abbrev import state_abbrev
import smtplib
import time
import traceback
import urllib.parse
import urllib.request

_HEADERS = {'User-Agent': 'Mozilla/5.0'}
_REQ_DELAY = 0.5
_EMAIL_RECIPIENTS = ['agoessling@gmail.com', 'michael.scarito@gmail.com']

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
_ASO_URLS = [
    'https://www.aso.com/listings/AircraftListings.aspx' +
    '?mg_id=171&act_id=1&mmg=true',
]
_AIRPLANE_MART_URLS = [
    'http://airplanemart.com/airplane-for-sale/specific-listing/M20J/351/',
    'http://airplanemart.com/airplane-for-sale/specific-listing/M20K/352/',
    'http://airplanemart.com/airplane-for-sale/specific-listing/M20M/348/'
]

def HandleParseError(description):
  def HandleParseErrorDecorator(func):
    @functools.wraps(func)
    def func_wrapper(url, *args, **kwargs):
      try:
        return func(url, *args, **kwargs)
      except KeyboardInterrupt:
        raise
      except:
        logger.exception('Error parsing {}: {}'.format(description, url))

        if cmd_args.email:
          SendEmail('Error in {}'.format(description.title()),
              'Problem parsing <a href="{}">{}</a>.<pre>\n\n{}</pre>'.format(
                  url, description, traceback.format_exc()))

        if cmd_args.try_continue:
          return None
        else:
          raise
    return func_wrapper
  return HandleParseErrorDecorator

def SendEmail(subject, body):
  session = smtplib.SMTP('smtp.gmail.com', 587)
  session.ehlo()
  session.starttls()
  session.ehlo()
  session.login('agoessling@gmail.com', 'yedvoxtyqrbludsf')

  text = '\r\n'.join([
      'From: Mooney Scraper',
      'Subject: ' + subject,
      'To: ' + ', '.join(_EMAIL_RECIPIENTS),
      'MIME-Version: 1.0',
      'Content-Type: text/html',
      '\r\n',
      body])

  session.sendmail('agoessling@gmail.com', _EMAIL_RECIPIENTS, text)

def SendNewListingEmail(new_listings):
  subject = 'Found {:d} New Listings'.format(len(new_listings))
  body = '<h4>Found {:d} new listings:</h4>'.format(len(new_listings))
  body += '<ul>'
  for listing in new_listings:
    body += '<li><a href="http://23.92.25.110/listing/{}/">{}</a></li>'.format(
        listing.id, listing.title)
  body += '</ul>'
  SendEmail(subject, body)

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

@HandleParseError('Trade-A-Plane listing')
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
    overhaul_strs = overhaul_str.split()
    if len(overhaul_strs) > 0:
      listing.engine_hours = float(overhaul_strs[0].replace(',', ''))
    if len(overhaul_strs) > 1:
      listing.overhaul_type = overhaul_strs[1]

  location_str = FindTradeAPlaneSpec(soup.find('label', string='Location:'),
      'next_sibling')
  if location_str:
    location_strs = location_str.split(',')
    if len(location_strs) == 1:
      listing.state = SanitizeState(location_strs[0].split()[0]\
          .replace('\n', ''))
    elif len(location_strs) == 2:
      listing.city = location_strs[0]
      listing.state = SanitizeState(location_strs[1].strip().split()[0]\
          .replace('\n', ''))

  listing.gps = FindGps(html)
  listing.transponder = FindTransponder(html)

  return listing

@HandleParseError('Trade-A-Plane summary')
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

    listing = ParseTradeAPlaneListing(listing_url)
    if not listing:
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

@HandleParseError('Controller listing')
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

@HandleParseError('Controller summary')
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

    listing = ParseControllerListing(listing_url)
    if not listing:
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

@HandleParseError('ASO listing')
def ParseAsoListing(url):
  request = urllib.request.Request(url, headers=_HEADERS)
  html = urllib.request.urlopen(request).read().decode('utf-8')
  soup = bs4.BeautifulSoup(html, 'lxml')
  listing = Listing()

  listing.title = soup.find(
      'div', class_='adSpecView-header-Descr').find('div').string.strip()
  listing.url = url

  spans = soup.find_all('span')
  for span in spans:
    if span.find(text=re.compile(r'Price')):
      price_str = re.sub(r'[^(\d\.)]', '', span.next_element)
      if price_str:
        listing.price = float(price_str)
    elif span.find(text=re.compile(r'Reg #')):
      listing.registration = span.next_element.split()[-1].upper()
    elif span.find(text=re.compile(r'Serial #')):
      listing.serial = span.next_element.split()[-1].upper()
    elif span.find(text=re.compile(r'TTAF:')):
      hours_str = re.sub(r'[^(\d\.)]', '', span.next_element)
      if hours_str:
        listing.airframe_hours = float(hours_str)
    elif span.find(text=re.compile(r'Location:')):
      locations = span.next_element.split()
      if len(locations) > 1:
        listing.state = SanitizeState(locations[1].strip(' ,'))

  year = re.search(r'(19|20)\d\d', listing.title)
  if year:
    listing.year = int(year.group(0))

  model = re.search(r'M20[A-Z]\s*(\d{3})?', listing.title.upper())
  if model:
    listing.model = model.group(0)

  engine_table = soup.find('table', class_='enginePropView')
  if engine_table:
    rows = engine_table.find_all('tr')
    if len(rows) == 2:
      for i, col in enumerate(rows[1].find_all('td')):
        if not re.search(r'[^\d]', col.string):
          listing.engine_hours = float(col.string)
          listing.overhaul_type = rows[0].find_all('td')[i].string.upper()
          break

  listing.gps = FindGps(html)
  listing.transponder = FindTransponder(html)

  return listing

@HandleParseError('ASO summary')
def ParseAsoSummary(url):
  logger.info('Scraping ASO Summary: {}'.format(url))

  load_time = time.time()

  request = urllib.request.Request(url, headers=_HEADERS)
  soup = bs4.BeautifulSoup(urllib.request.urlopen(request), 'lxml')
  links = soup.find_all('a', class_='photoListingsDescription')
  links = [x for x in links if not x.find('img')]

  logger.info('Found {:d} ASO listings.'.format(len(links)))

  new_listings = []

  for link in links:
    while time.time() < load_time + _REQ_DELAY:
      time.sleep(0.1)

    listing_url = urllib.parse.urljoin(url, link['href'])
    try:
      Listing.get(Listing.url == listing_url)
      logger.info('Skipping {}.'.format(link.string.strip()))
      continue
    except peewee.DoesNotExist:
      logger.info('Opening {}.'.format(link.string.strip()))

    load_time = time.time()

    listing = ParseAsoListing(listing_url)
    if not listing:
      continue

    if listing.registration:
      try:
        Listing.get(Listing.registration == listing.registration)
        logger.info('Duplicate Registration {}: {}.'.format(
            listing.registration,
            link.string.strip()))
        continue
      except peewee.DoesNotExist:
        pass

    listing.save()
    new_listings.append(listing)

  return new_listings

def FindAirplaneMartSpec(soup, label, func=None):
  price_tag = soup.find(text=re.compile(label))
  if price_tag:
    label_td = price_tag.find_parent('td')
    value_td = label_td.find_next_sibling('td')
    value_string = value_td.find('font').string
    if value_string:
      if func == float or func == int:
        value_string = re.sub(r'[^(0-9\.)]', '', value_string)
        return func(value_string)
      elif func:
        return func(value_string)
      else:
        return value_string

@HandleParseError('Airplane Mart listing')
def ParseAirplaneMartListing(url):
  request = urllib.request.Request(url, headers=_HEADERS)
  html = urllib.request.urlopen(request).read().decode('utf-8', 'ignore')
  soup = bs4.BeautifulSoup(html, 'lxml')
  listing = Listing()

  listing.title = soup.find('font', size='5').find('b').string.strip()
  listing.url = url

  price_str = re.sub(r'[^(\d\.)]', '', FindAirplaneMartSpec(soup, 'Price:'))
  if price_str:
    listing.price = float(price_str)

  listing.registration = FindAirplaneMartSpec(soup, 'Registration:')
  listing.serial = FindAirplaneMartSpec(soup, 'Serial:')
  listing.airframe_hours = FindAirplaneMartSpec(soup, 'Airframe Time:', float)

  engine_str = FindAirplaneMartSpec(soup, 'Engine Time\(s\):')
  if engine_str:
    match = re.search(r'([0-9\.]+)(?:\s+([A-Z]+))?', engine_str.upper())
    if match:
      listing.engine_hours = float(match.group(1))
      if len(match.groups()) >= 2:
        listing.overhaul_type = match.group(2)

  location_str = FindAirplaneMartSpec(soup, 'Aircraft Location:')
  if location_str:
    location_str = re.sub(r'\s*\(.*\)\s*', '', location_str)
    if location_str:
      locations = location_str.split(',')
      listing.city = locations[0].strip()
      if len(locations) >= 2:
        listing.state = SanitizeState(locations[1].split()[0].strip())

  year = re.search(r'(19|20)\d\d', listing.title)
  if year:
    listing.year = int(year.group(0))

  model = re.search(r'M20[A-Z]\s*(\d{3})?', listing.title.upper())
  if model:
    listing.model = model.group(0)

  listing.gps = FindGps(html)
  listing.transponder = FindTransponder(html)

  return listing

@HandleParseError('Airplane Mart summary')
def ParseAirplaneMartSummary(url):
  logger.info('Scraping Airplane Mart Summary: {}'.format(url))

  load_time = time.time()

  request = urllib.request.Request(url, headers=_HEADERS)
  soup = bs4.BeautifulSoup(urllib.request.urlopen(request), 'lxml')
  links = soup.find_all('a',
      href=re.compile(r'/aircraft-for-sale/Single-Engine-Piston/'))

  logger.info('Found {:d} Airplane Mart listings.'.format(len(links)))

  new_listings = []

  for link in links:
    while time.time() < load_time + _REQ_DELAY:
      time.sleep(0.1)

    listing_url = urllib.parse.urljoin(url, link['href'])
    try:
      Listing.get(Listing.url == listing_url)
      logger.info('Skipping {}.'.format(link.find('b').string.strip()))
      continue
    except peewee.DoesNotExist:
      logger.info('Opening {}.'.format(link.find('b').string.strip()))

    load_time = time.time()

    listing = ParseAirplaneMartListing(listing_url)
    if not listing:
      continue

    if listing.registration:
      try:
        Listing.get(Listing.registration == listing.registration)
        logger.info('Duplicate Registration {}: {}.'.format(
            listing.registration,
            link.find('b').string.strip()))
        continue
      except peewee.DoesNotExist:
        pass

    listing.save()
    new_listings.append(listing)

  return new_listings

if __name__ == '__main__':
  try:
    parser = argparse.ArgumentParser(
        description='Scrapes web for aircraft sales listings.')
    parser.add_argument('--log-file',
        help='Path to log file.  Defaults to stdout.')
    parser.add_argument('--verbose', action='store_true',
        help='Verbose logging information.')
    parser.add_argument('--email', action='store_true',
        help='Send error and new listing emails.')
    parser.add_argument('--try-continue', action='store_true',
        help='Log and continue on error.')
    cmd_args = parser.parse_args()

    logger = logging.getLogger('Scraper')

    if cmd_args.verbose:
      level = logging.DEBUG
      formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    else:
      level = logging.INFO
      formatter = logging.Formatter('[%(levelname)s] %(message)s')

    if cmd_args.log_file:
      handler = logging.FileHandler(cmd_args.log_file)
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
      listings = ParseControllerSummary(url)
      if listings:
        new_listings += listings

    for url in _TRADE_A_PLANE_URLS:
      listings = ParseTradeAPlaneSummary(url)
      if listings:
        new_listings += listings

    for url in _ASO_URLS:
      listings = ParseAsoSummary(url)
      if listings:
        new_listings += listings

    for url in _AIRPLANE_MART_URLS:
      listings = ParseAirplaneMartSummary(url)
      if listings:
        new_listings += listings

    logger.info('Found {:d} new listings.'.format(len(new_listings)))

    if new_listings:
      SendNewListingEmail(new_listings)

  except KeyboardInterrupt:
    raise
  except:
    logger.exception('Error in scraper.')

    if cmd_args.email:
      SendEmail('Error in Scraper',
          'Problem in scraper script.<pre>\n\n{}</pre>'.format(
              traceback.format_exc()))
    raise
