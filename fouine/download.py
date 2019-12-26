import gzip
import pathlib
import tempfile
import re
import shutil

import typing as ty

import requests
import tqdm

from typing_extensions import Literal

# Python < 3.8 shim
try:
    from gzip import BadGzipFile  # type: ignore # (silence mypy for < 3.8)
except ImportError:
    BadGzipFile = OSError


def download(
    source: str,
    target_dir: ty.Union[str, pathlib.Path],
    dest_name: ty.Optional[str] = None,
    unpack: Literal["ifneedbe", True, False] = "ifneedbe",
    overwrite: bool = True,
) -> pathlib.Path:
    """Download a file from an url, optionally unpacking archives.

    Arguments
    =========

    :source: The url to download from
    :target_dir: The path to the dir to download to, will be created if it does not exist
    :dest_name: The name of the destination, whether it is a file or a directory, it not given, it
      will be inferred from the reponse headers or in last resort from `source`.
    :unpack: Whether to attempt to unpack the downloaded file. In that case, we defer to
    `shutil.unpack_archive` to infer the archive format and the operation will fail if the archive
    contains anything else than a single file or a single directory. If `shutil` didn't work, we
    also try to unpack the source as if it were a single gzip'd file.
    :overwrite: Whether to overwrite the destination if it already exists

    Return
    ======

    The path to the destination
    """
    r = requests.get(source, stream=True, allow_redirects=True)

    if r.status_code != 200:
        # FIXME: not the correct exception sublass
        raise ValueError(
            f"Couldn't reach {source}, server answered with status code {r.status_code}"
        )
    m = re.search('filename="(.*?)"', r.headers.get('content-disposition', ''))
    if m is not None:
        source_file_name = m[1]
    else:
        source_file_name = source.rsplit('/', 1)[-1]
    if dest_name is None:
        dest_name = source_file_name
    target_dir = pathlib.Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / dest_name
    # Fail early
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} already exists")
    total_size = int(r.headers.get('content-length', 0))
    block_size = 1024
    with tempfile.TemporaryDirectory() as download_dir:
        f: pathlib.Path = pathlib.Path(download_dir) / source_file_name
        with open(f, "wb") as out_stream:
            with tqdm.tqdm(
                total=total_size,
                unit='iB',
                unit_divisor=1024,
                unit_scale=True,
                leave=False,
                mininterval=0.5,
            ) as pbar:
                for block in r.iter_content(block_size):
                    out_stream.write(block)
                    pbar.update(block_size)
            out_stream.flush()
        if unpack:
            # This will be deleted with `download_dir`, we don't need to housekeep
            unpack_dir = pathlib.Path(tempfile.mkdtemp(dir=download_dir))
            try:
                shutil.unpack_archive(f, unpack_dir)
                archive_content = list(pathlib.Path(unpack_dir).glob("*"))
                if len(archive_content) == 0:
                    raise ValueError(f"Archive {f} is empty")
                elif len(archive_content) > 1:
                    raise ValueError(f"Archive {f} is a tarbomb")
                f = archive_content[0]
            except shutil.ReadError:
                try:
                    f = ungzip(f, unpack_dir / f"{f.name}_uncompressed")
                except BadGzipFile:
                    if unpack != "ifneedbe":
                        raise ValueError(f"{f} isn't a valid archive")

        # FIXME: this could be made more atomic
        if target.exists():
            # To avoid the stupid behaviour of shutil.move when the target is a dir
            if target.is_dir():
                shutil.rmtree(target)
            # `shutil.move` will not necessarily do this itself
            elif f.is_dir():
                target.unlink()
        res = shutil.move(str(f), str(target))
    return pathlib.Path(res)


def ungzip(source, target):
    with gzip.open(source, 'rb') as uncompress, open(target, 'wb') as out_stream:
        shutil.copyfileobj(uncompress, out_stream)
    return target
