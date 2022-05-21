#!/usr/bin/env python3

import re

URL_CATALOG_INDEX = 'http://202.96.31.36:8888/reading/list/{year}_pm_0_a5b1b3db-8656-4474-8055-fb3eb52bf458?p={page}'
URL_CATALOG_INDEX_NOPAGE = 'http://202.96.31.36:8888/reading/list/{year}_pm_0_a5b1b3db-8656-4474-8055-fb3eb52bf458'
URL_BOOK_CONTAINER = 'http://202.96.31.36:8888/Reading/Show/{book_uuid}'

PREFIX_FLASH = 'flipbooks'
PREFIX_HTML5 = 'fliphtml5'

URL_BOOK_PREFIX = 'http://202.96.31.36:8888/{prefix}/password/main/qikan/etwx/{year}/{month}/{series}/web/'
URL_BOOK_META = 'http://202.96.31.36:8888/{prefix}/password/main/qikan/etwx/{year}/{month}/{series}/web/{name}.xml'

RE_BOOK_UUID_FROM_HOME = re.compile(r'^/Reading/Detail/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', flags=re.IGNORECASE)
RE_BOOK_META = re.compile(r'^/(fliphtml5|flipbooks)/password/main/qikan/etwx/([^/]+)/([^/]+)/([^/]+)/web/([^/_]+)_opf_files')

OFFLINE_LICENSE_PASSPHRASE = '0b8b6a4650b148a1975331bc2da63f93'
PASSWORD_PASSPHRASE_SUFFIX = '885d813a749641888o2b414729bb0dcb'
