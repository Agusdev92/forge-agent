import os


def exists(path):
    return os.path.exists(path)


def is_dir(path):
    return os.path.isdir(path)


def join(*paths):
    return os.path.join(*paths)


def absolute(path):
    return os.path.abspath(path)


class FileSystem:
    def __init__(self, path="."):
        self.path = path

    def list_files(self):
        return [
            f for f in os.listdir(self.path)
            if os.path.isfile(os.path.join(self.path, f))
        ]

    def list_directories(self):
        return [
            d for d in os.listdir(self.path)
            if os.path.isdir(os.path.join(self.path, d))
        ]
