from pathlib import Path


class Scanner:
    def __init__(self, path="."):
        self.path = Path(path)

    def scan(self):
        py_files = list(self.path.rglob("*.py"))

        empty = 0
        todos = 0

        for file in py_files:
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if not text.strip():
                empty += 1

            todos += text.count("TODO")

        print("🔎 Forge Scan\n")
        print(f"🐍 Python files: {len(py_files)}")
        print(f"⚠️ TODO encontrados: {todos}")
        print(f"📄 Archivos vacíos: {empty}")
