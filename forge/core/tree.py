from os import listdir
from os.path import isdir, join


class Tree:
    def __init__(self, path="."):
        self.path = path

    def show(self):
        print("📦 Proyecto\n")

        items = sorted(listdir(self.path))

        for item in items:
            if item.startswith("."):
                continue

            full_path = join(self.path, item)

            if isdir(full_path):
                print(f"📁 {item}")
            else:
                print(f"📄 {item}")
