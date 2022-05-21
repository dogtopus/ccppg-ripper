# CCPPG ripping tool

Downloads CCPPG FlipViewer flash eBooks and rips them as standard format.

Currently hardcoded to download Er Tong Wen Xue from the [NLC](http://www.nlc.cn) endpoint but can be easily adapted to download any book/newspaper archives available on NLC and other public (e.g. Guangdong) endpoints.

## Getting started

Make sure you have poetry installed, then

```sh
poetry install
```

For `book-converter` command you also need to have JPEXS Flash Decompiler installed.

## Usage

```sh
poetry run <catalog-downloader|metadata-downloader|decrypt-object|book-converter|decrypt-access-code> ...
```
