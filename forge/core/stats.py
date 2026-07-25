from os import walk
from forge.core.project import Project


class Stats:
    def __init__(self, path="."):
        self.path = path

    def show(self):
        project = Project(self.path)

        folders = 0
        files = 0

        for _, dirs, filenames in walk(self.path):
            folders += len(dirs)
            files += len(filenames)

        print("📊 Forge Stats\n")
        print(f"🐍 Lenguaje: {project.detect_language()}")
        print(f"📂 Carpetas: {folders}")
        print(f"📄 Archivos: {files}")
