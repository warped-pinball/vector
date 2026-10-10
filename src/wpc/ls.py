import os


def ls(top):
    """List all files in a directory tree."""
    try:
        entries = os.listdir(top)
    except OSError:
        return

    for entry in entries:
        path = top + "/" + entry if top != "/" else "/" + entry
        try:
            mode = os.stat(path)[0]
        except OSError:
            continue
        # 0x4000 is the S_IFDIR flag indicating a directory
        if mode & 0x4000:
            yield from ls(path)
        else:
            yield path
