#!/usr/bin/env python3
from typing import Optional, Literal, List, Sequence, cast

import subprocess
import pathlib
import tempfile

from lxml import etree
import tqdm
import pikepdf

from .downloader import extract_license_url, extract_page
from . import crypteww


class FFDecWrapper:
    _ffdec: List[str]

    def __init__(self, exe: str, java: Optional[str] = None, jvm_options: Optional[List[str]] = None):
        self._ffdec = []
        if java is not None:
            self._ffdec.append(java)
            if jvm_options is not None:
                self._ffdec.extend(jvm_options)
            self._ffdec.append('-jar')
        self._ffdec.append(exe)
        self._ffdec.append('-cli')

    def call(self, args: Sequence[str]):
        ffdec_args = self._ffdec.copy()
        ffdec_args.extend(args)
        return subprocess.run(ffdec_args, capture_output=True, check=True)

    def extract_character(self,
                          input_file: pathlib.Path,
                          output_path: pathlib.Path,
                          object_type: str,
                          character_id: int) -> Optional[pathlib.Path]:
        self.call([
            '-selectid',
            str(character_id),
            '-export',
            object_type,
            str(output_path.absolute()),
            str(input_file.absolute()),
        ])

        for entry in output_path.glob(f'{character_id}.*'):
            if entry.is_file():
                return entry
        return None

    def render_frames_as_pdf(self, input_file: pathlib.Path, output_path: pathlib.Path):
        self.call([
            '-format',
            'frame:pdf',
            '-export',
            'frame',
            str(output_path.absolute()),
            str(input_file.absolute()),
        ])

        output_pdf = output_path / 'frames.pdf'
        if output_pdf.is_file():
            return output_pdf
        return None


def get_book_master_passphrase_from_license(license_path: pathlib.Path):
    with license_path.open('rb') as license_file:
        license_root = etree.parse(license_file).getroot()

    encryption_xp = cast(List[etree._Element], license_root.xpath('/package/certificate/security/encryption'))
    if len(encryption_xp) != 1:
        raise RuntimeError('Invalid use of encryption tag.')

    epassphrase = encryption_xp[0].get('content')
    if epassphrase is None:
        raise RuntimeError('Encryption tag does not contain the encrypted passphrase.')

    return crypteww.decrypt_offline_license_passphrase(epassphrase)

def get_book_access_code_from_license(license_path: pathlib.Path):
    # TODO this is a bit ugly. Maybe refactor it a bit?
    passphrase = get_book_master_passphrase_from_license(license_path)

    with license_path.open('rb') as license_file:
        license_root = etree.parse(license_file).getroot()

    password_xp = cast(List[etree._Element], license_root.xpath('/package/certificate/security/password'))
    if len(password_xp) != 1:
        raise RuntimeError('Invalid use of password tag.')

    epassword = password_xp[0].get('content')
    if epassword is None:
        raise RuntimeError('Password tag does not contain the encrypted password.')

    return crypteww.decrypt_access_code_passphrase(passphrase, epassword)

def get_book_master_passphrase_from_metadata(book_path: pathlib.Path, metadata_xml: etree._Element):
    license_path = book_path / extract_license_url(metadata_xml)
    return get_book_master_passphrase_from_license(license_path)

def convert_book(book_xml_path: pathlib.Path, output_path: pathlib.Path, output_type: Literal['cbz', 'pdf'] = 'pdf'):
    with book_xml_path.open('rb') as metadata_xml_file:
        metadata_xml = etree.parse(metadata_xml_file).getroot()

    book_prefix = book_xml_path.parent
    passphrase = get_book_master_passphrase_from_metadata(book_prefix, metadata_xml)

    # output-type specific
    output = pikepdf.Pdf.new()

    with tempfile.TemporaryDirectory() as work_dir_name, output:
        work_dir = pathlib.Path(work_dir_name)
        pages = tuple(extract_page(metadata_xml))

        for page_url, mime_type in tqdm.tqdm(pages):
            page_path = book_prefix / pathlib.PurePosixPath(page_url)
            decrypted_obj_path = work_dir / 'decrypted_obj'
            frame: Optional[pathlib.Path] = None

            # Prepare input file
            with page_path.open('rb') as page_file, decrypted_obj_path.open('wb') as decrypted_obj:
                crypteww.decrypt_swf_obj_file(passphrase, page_file, decrypted_obj)

            # Render the frame
            if mime_type == 'application/x-shockwave-flash':
                ffdec = FFDecWrapper('ffdec')
                # output-type specific
                frame = ffdec.render_frames_as_pdf(decrypted_obj_path, work_dir / 'output')
            else:
                #raise RuntimeError(f'Unhandled page MIME type {mime_type} for file {page_path}.')
                print(f'Unhandled page MIME type {mime_type} for file {page_path}. Skipped.')
                continue

            if frame is None:
                raise RuntimeError(f'Failed to produce an output for {page_path}.')

            # output-type specific
            with pikepdf.Pdf.open(frame) as frame_pdf:
                if len(frame_pdf.pages) > 1:
                    print(f'Multiple page generated for {page_path}, including all of them.')
                output.pages.extend(frame_pdf.pages)
            frame.unlink()

        # output-type specific
        output.remove_unreferenced_resources()
        output.save(output_path)
