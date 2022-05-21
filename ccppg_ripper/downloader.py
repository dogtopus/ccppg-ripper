#!/usr/bin/env python3

from typing import Set, Literal, Optional, Tuple, List, Iterator, cast
import datetime
import io
import json
import os
import pathlib
import posixpath
import random
import time
import urllib.parse
import zipfile

from dateutil.parser import parse as parsedate
from lxml import etree
import requests

from . import constants
from .page import BookMetadata

AssetFlags = Set[Literal[
    #'bg',
    'thumbnails',
    'searchabletext',
    #'cover',
    'archive',
    'toc',
    #'iframe',
]]


def prefix_from_book_metadata(book: BookMetadata) -> str:
    return f"{book['year']}_{book['month']}_{book['series']}_{book['name']}_{book['uuid']}"

def extract_license_url(metadata_xml: etree._Element) -> str:
    # TODO XPath object doesn't always have len()?
    license_tags = cast(List[etree._Element], metadata_xml.xpath('/package/drm_enabled/certificate'))
    if len(license_tags) != 1:
        raise RuntimeError('Certificate entry must occur exactly once.')

    license_tag = license_tags[0]
    if license_tag.get('type') != '2':
        raise RuntimeError('Only embedded license is supported.')

    url = license_tag.get('url')
    if url is None:
        raise RuntimeError('License file URL missing.')
    return url

def extract_page(metadata_xml: etree._Element) -> Iterator[Tuple[str, str]]:
    manifest_items = cast(List[etree._Element], metadata_xml.xpath('/package/manifest/item'))
    if len(manifest_items) == 0:
        raise RuntimeError('No pages found.')

    for item in manifest_items:
        url = item.get('href')
        mime_type = item.get('media-type')

        if url is None:
            raise RuntimeError(f'URL is missing for item tag {item}.')
        if mime_type is None:
            print('MIME type is missing. Guessing from the suffix...')
            if url.endswith('.swf'):
                mime_type = 'application/x-shockwave-flash'
            elif url.endswith('.png') or url.endswith('.jpg') or url.endswith('.gif'):
                mime_type = 'image/x-flp'
            else:
                raise RuntimeError(f'Cannot determine MIME type for item tag {item}.')

        yield url, mime_type

def extract_asset_urls(metadata_xml: etree._Element, include: Optional[AssetFlags] = None):
    result: List[str] = []

    root = metadata_xml

    # Pages (required)
    result.extend(url for url, _mime_type in extract_page(root))

    # License (required)
    result.append(extract_license_url(metadata_xml))

    if include is None:
        return result

    # Thumbnails
    if 'thumbnails' in include:
        thumbnail_items = cast(List[etree._Element], root.xpath('/package/spine/itemref'))
        if len(thumbnail_items) == 0:
            print('No thumbnails found.')

        for item in thumbnail_items:
            result.append(item.get('thumbnail'))

    # Text
    if 'searchabletext' in include:
        text_items = cast(List[etree._Element], root.xpath('/package/drm_enabled/searchabletext'))
        if len(text_items) == 1:
            result.append(text_items[0].get('url'))

    # Archive
    if 'searchabletext' in include:
        archive_items = cast(List[etree._Element], root.xpath('/package/drm_enabled/archive'))
        if len(archive_items) == 1:
            result.append(archive_items[0].get('url'))

    # TOC
    # TODO embedded TOC
    if 'searchabletext' in include:
        toc_items = cast(List[etree._Element], root.xpath('/package/drm_enabled/customized/pagedescription'))
        if len(toc_items) == 1:
            external_toc = toc_items[0].get('external')
            if external_toc is not None:
                result.append(external_toc)
            else:
                print('TOC requested but no TOC file found.')

    return result

def fetch_metadata_xml(metadata: BookMetadata) -> Tuple[datetime.datetime, bytes]:
    url = constants.URL_BOOK_META.format(
        prefix=metadata['prefix'],
        year=metadata['year'],
        month=metadata['month'],
        series=metadata['series'],
        name=metadata['name'],
    )

    req = requests.get(url)
    date = parsedate(req.headers['last-modified'])

    return date, req.content

def read_catalog_zip(catalog_zip: zipfile.ZipFile) -> Iterator[BookMetadata]:
    for filename in catalog_zip.namelist():
        with catalog_zip.open(filename, mode='r') as metadata_bytes:
            with io.TextIOWrapper(metadata_bytes, encoding='utf-8') as metadata_file:
                metadata: List[BookMetadata] = json.load(metadata_file)
        yield from metadata

def generate_url_list(prefix: str, book_prefix: pathlib.Path, files: List[str], downloader: Literal['aria2', 'wget']):
    lines = []
    for file in files:
        abs_url = urllib.parse.urljoin(prefix, file)
        if downloader == 'aria2':
            local_prefix = book_prefix / pathlib.PurePosixPath(posixpath.dirname(file))
            lines.append(abs_url)
            lines.append(f"    dir = {posixpath.join('.', local_prefix)}")
        else:
            lines.append(abs_url)
    return '\n'.join(lines)

def generate_skel_dir_from_catalog(catalog_zip: zipfile.ZipFile, output_dir: pathlib.Path, downloader: Literal['aria2', 'wget'] = 'aria2', from_local_data: bool = False):
    if not output_dir.exists():
        output_dir.mkdir()
    if not output_dir.is_dir():
        raise ValueError('Output path is not a directory.')
    
    with (output_dir / 'assets.lst').open('w') as assets_download_list:
        for book in read_catalog_zip(catalog_zip):
            prefix = prefix_from_book_metadata(book)

            print(f'Processing book {prefix}...')

            book_dir = output_dir / prefix
            book_dir_prefix_only = pathlib.Path(prefix)
            metadata_xml_path = book_dir / f"{book['name']}.xml"

            if not (book_dir.exists() and metadata_xml_path.exists()):
                if from_local_data:
                    raise FileNotFoundError(f'Metadata {metadata_xml_path} does not exist and downloader is running in local mode.')
                book_dir.mkdir(exist_ok=True)

                # Download metadata XML
                print(f'Downloading {metadata_xml_path}...')

                mtime, metadata_xml = fetch_metadata_xml(book)
                metadata_xml_path.write_bytes(metadata_xml)
                os.utime(metadata_xml_path, times=(mtime.timestamp(), mtime.timestamp()))

                metadata_xml_root = etree.fromstring(metadata_xml)

                print('Sleeping...')
                time.sleep(3 + random.expovariate(3) * 10)
                print('Done sleeping.')
            else:
                print('Using cached data')
                with metadata_xml_path.open('rb') as metadata_xml_file:
                    metadata_xml_root = etree.parse(metadata_xml_file).getroot()

            # Generate and write URL list
            url_book_prefix = constants.URL_BOOK_PREFIX.format(
                prefix=book['prefix'],
                year=book['year'],
                month=book['month'],
                series=book['series'],
            )

            asset_urls = extract_asset_urls(metadata_xml_root, {'searchabletext', 'archive', 'toc'})
            assets_download_list.write(generate_url_list(url_book_prefix, book_dir_prefix_only, asset_urls, downloader))
            assets_download_list.write('\n')
