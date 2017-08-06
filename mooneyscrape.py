#!/usr/bin/python3

import bs4
import pprint
import re
import time
import urllib

pp = pprint.PrettyPrinter(indent=2)

_HEADERS = {'User-Agent': 'Mozilla/5.0'}
_REQ_DELAY = 0.5
url = 'https://www.controller.com/listings/aircraft/for-sale/list/category/13/aircraft/manufacturer/mooney/model-group/m20j'

class Listing(object):
  def __init__(self):
    self.title = None
    self.url = None
    self.price = None
    self.year = None
    self.registration = None
    self.model = None
    self.serial = None
    self.overhaul_hours = None
    self.overhaul_type = None
    self.airframe_time = None

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
    listing_url = div.a['href']
    load_time = time.time()
    #listing = ParseControllerListing(listing_url)
    #pp.pprint(listing)
    #listings.append(listing)

  return listings


def ParseControllerSummary(url):
  load_time = time.time()

  request = urllib.request.Request(url, headers=_HEADERS)
  soup = bs4.BeautifulSoup(urllib.request.urlopen(request), 'lxml')

  name_divs = soup.find_all('div', class_='listing-name')

  print('Found {:d} listings.'.format(len(name_divs)))

  listings = []

  for div in name_divs:
    while time.time() < load_time + _REQ_DELAY:
      time.sleep(0.1)

    print('Opening {}.'.format(div.a.string))
    listing_url = urllib.parse.urljoin(url, div.a['href'])
    load_time = time.time()
    listing = ParseControllerListing(listing_url)
    pp.pprint(listing)
    listings.append(listing)

  return listings

def ParseControllerListing(url):
  request = urllib.request.Request(url, headers=_HEADERS)
  soup = bs4.BeautifulSoup(urllib.request.urlopen(request), 'lxml')
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
  listing.airframe_time = FindControllerSpec(soup, 'Total Time', float)

  overhaul_str = FindControllerSpec(soup, 'Overhaul')
  if overhaul_str:
    listing.overhaul_hours = float(overhaul_str.split(' ')[0].replace(',', ''))
    listing.overhaul_type = overhaul_str.split(' ')[1]

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
  ParseTradeAPlaneSummary('file:///home/agoessling/Downloads/tradeaplane_main.html')
