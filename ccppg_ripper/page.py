#!/usr/bin/env python3

from typing import Optional, List, TypedDict, Iterator, Tuple, cast

import random
import time

import mechanicalsoup
from bs4 import BeautifulSoup, NavigableString
from bs4.element import Tag

from .constants import *


class BookMetadata(TypedDict):
    uuid: Optional[str]
    prefix: str
    year: str
    month: str
    series: str
    name: str


def new_browser() -> mechanicalsoup.StatefulBrowser:
    return mechanicalsoup.StatefulBrowser(
        soup_config={'features': 'lxml'},
        raise_on_404=True,
        user_agent='Mozilla/5.0 (X11; Linux x86_64; rv:100.0) Gecko/20100101 Firefox/100.0',
    )

def has_next_page(soup: BeautifulSoup) -> bool:
    page_bar = soup.find('div', attrs={'id': 'pageBar'})
    if page_bar is None or isinstance(page_bar, NavigableString):
        return False
    return page_bar.find(text='下一页') is not None

def parse_catalog(soup: BeautifulSoup) -> List[BookMetadata]:
    ul: Optional[Tag] = soup.ul

    if ul is None:
        raise RuntimeError('Cannot locate book listing.')

    result: List[BookMetadata] = []

    for element in ul.find_all('li', recursive=False):
        #print(element.find_all('a'))
        uuid: Optional[str] = None
        uuid_match = RE_BOOK_UUID_FROM_HOME.match(element.div.a['href'])
        if uuid_match is not None:
            uuid = cast(str, uuid_match.group(1))

        thumbnail_url = element.div.a.img['src']

        meta_match = RE_BOOK_META.match(thumbnail_url)
        if meta_match is not None:
            meta: BookMetadata = {
                'uuid': uuid,
                'prefix': cast(str, meta_match.group(1)),
                'year': cast(str, meta_match.group(2)),
                'month': cast(str, meta_match.group(3)),
                'series': cast(str, meta_match.group(4)),
                'name': cast(str, meta_match.group(5)),
            }

            result.append(meta)
    
    return result

def download_catalog(years: List[int | str]) -> Iterator[Tuple[int | str, int, List[BookMetadata]]]:
    browser = new_browser()

    for year in years:
        url = URL_CATALOG_INDEX_NOPAGE.format(year=year)
        browser.open(url)
        page = 1

        while True:
            print(f'Parsing {browser.url}...')
            parsed_catalog = parse_catalog(browser.page)
            yield year, page, parsed_catalog

            print('Sleeping...')
            time.sleep(3 + random.expovariate(3) * 15)
            print('Navigating next page...')

            page += 1

            try:
                next_page_link: Tag = browser.find_link(link_text='下一页')
            except mechanicalsoup.LinkNotFoundError:
                print('Last page.')
                break
            browser.follow_link(next_page_link)
