from typing import Sequence, Iterator

import argparse
import io
import json
import pathlib
import zipfile

from . import page
from . import downloader
from . import converter
from . import crypteww

def catalog_downloader():
    def _parse_args():
        p = argparse.ArgumentParser(help='Download catalog per year. Currently only supports the NLC (National Library of China) endpoint.')
        p.add_argument('-d', '--dry-run', action='store_true', default=False, help='Only prints actions.')
        p.add_argument('output', help='ZIP file that contains the downloaded metadata.')
        p.add_argument('years', nargs='+', help='Years to download. Can be a single year or in the format of xxxx-yyyy (double inclusive).')
        return p, p.parse_args()

    def _expand_years(years: Sequence[str]) -> Iterator[str]:
        for year in years:
            if '-' in year:
                first_year, last_year = map(int, year.split('-'))
                yield from map(str, range(first_year, last_year+1))
            else:
                yield year

    p, args = _parse_args()

    output_zip = zipfile.ZipFile(args.output, mode='a', compression=zipfile.ZIP_DEFLATED)

    if args.dry_run:
        for year in _expand_years(args.years):
            print(f'page.download_catalog({repr(year)})')
        return

    for year, pageno, parsed_catalog in page.download_catalog(_expand_years(args.years)):
        with output_zip.open(f'{year}_{pageno}.json', mode='w') as output_binary:
            with io.TextIOWrapper(output_binary, encoding='utf-8') as output:
                json.dump(parsed_catalog, output)

def metadata_downloader():
    def _parse_args():
        p = argparse.ArgumentParser(help='Download metadata, initialize FlipViewer eBook folder structure and populate the asset download list using a previously generated catalog ZIP file.')
        p.add_argument('catalog', help='ZIP file that contains the downloaded metadata.')
        p.add_argument('output', help='Output directory.')
        p.add_argument('--local', action='store_true', default=False, help='Generate download list only from local data.')
        p.add_argument('--downloader', default='aria2', help='Use this downloader.')
        return p, p.parse_args()

    p, args = _parse_args()
    output = pathlib.Path(args.output)
    with zipfile.ZipFile(args.catalog, mode='r') as catalog_zip:
        downloader.generate_skel_dir_from_catalog(catalog_zip, output, downloader=args.downloader, from_local_data=args.local)

def decrypt_access_code():
    def _parse_args():
        p = argparse.ArgumentParser('Decrypt the access code from a license file.')
        p.add_argument('license', type=pathlib.Path, help='License file.')
        return p, p.parse_args()

    p, args = _parse_args()

    access_code = converter.get_book_access_code_from_license(args.license)
    print(f'Access Code: {access_code}')

def decrypt_object():
    def _parse_args():
        p = argparse.ArgumentParser('Decrypt a single object.')
        p.add_argument('license', help='License file.')
        p.add_argument('encrypted', help='Encrypted object.')
        p.add_argument('decrypted', help='Path to store decrypted object.')
        return p, p.parse_args()

    p, args = _parse_args()
    dest_path = pathlib.Path(args.decrypted)
    src_path = pathlib.Path(args.encrypted)
    license_path = pathlib.Path(args.license)

    passphrase = converter.get_book_master_passphrase_from_license(license_path)
    with src_path.open('rb') as src_file, dest_path.open('wb') as dest_file:
        crypteww.decrypt_swf_obj_file(passphrase, src_file, dest_file)

def book_converter():
    def _parse_args():
        p = argparse.ArgumentParser('Rip a fully downloaded FlipViewer eBook as PDF.')
        p.add_argument('metadata', type=pathlib.Path, help='Metadata XML file. Must be in a valid FVX prefix.')
        p.add_argument('output', type=pathlib.Path, help='Path to output.')
        return p, p.parse_args()
    
    p, args = _parse_args()

    converter.convert_book(args.metadata, args.output)
