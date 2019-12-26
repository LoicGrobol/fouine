import filecmp
import pathlib
import tempfile

import responses

import fouine

import pytest


@pytest.fixture(params=["text_file.txt"])
def datafile(shared_datadir, request):
    return shared_datadir / request.param


@responses.activate
def test_downloads_file(datafile):
    url = f"http://example.org/{datafile.name}"
    with open(datafile, 'rb') as in_stream:
        responses.add(
            responses.GET,
            url,
            body=in_stream.read(),
            status=200,
            content_type='text',
            adding_headers={'Transfer-Encoding': 'chunked'},
        )
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = pathlib.Path(tempdir)
            filename = fouine.download(
                source=url, target_dir=tempdir_path, dest_name=datafile.name
            )
            assert filecmp.cmp(datafile, filename)
