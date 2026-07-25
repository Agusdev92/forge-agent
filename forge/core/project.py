from forge.core.filesystem import exists, is_dir, join, absolute, FileSystem


class Project:
    def __init__(self, path="."):
        self.path = path

    def detect_language(self):
        if exists(join(self.path, "requirements.txt")):
            return "Python"

        if exists(join(self.path, "package.json")):
            return "Node.js"

        return "Desconocido"

    def analyze(self):
        print(f"📁 Proyecto: {absolute(self.path)}")

        if is_dir(join(self.path, ".git")):
            print("✅ Git encontrado")
        else:
            print("❌ Git no encontrado")

        if exists(join(self.path, "requirements.txt")):
            print("✅ requirements.txt encontrado")
        else:
            print("❌ requirements.txt no encontrado")

        if is_dir(join(self.path, ".venv")):
            print("✅ Entorno virtual encontrado")
        else:
            print("❌ Entorno virtual no encontrado")

        print(f"🐍 Lenguaje: {self.detect_language()}")

        fs = FileSystem(self.path)

        print("\n📂 Carpetas")
        for folder in fs.list_directories():
            print(f" - {folder}")

        print("\n📄 Archivos")
        for file in fs.list_files():
            print(f" - {file}")
