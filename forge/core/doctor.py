from forge.core.filesystem import exists, is_dir, join


class Doctor:
    def __init__(self, path="."):
        self.path = path

    def check(self):
        print("🏥 Forge Doctor\n")

        score = 0
        total = 6

        checks = [
            ("Git", is_dir(join(self.path, ".git"))),
            ("Entorno virtual", is_dir(join(self.path, ".venv"))),
            ("requirements.txt", exists(join(self.path, "requirements.txt"))),
            ("README.md", exists(join(self.path, "README.md"))),
            (".gitignore", exists(join(self.path, ".gitignore"))),
            ("tests", is_dir(join(self.path, "tests"))),
        ]

        for name, ok in checks:
            if ok:
                print(f"✅ {name}")
                score += 1
            else:
                print(f"❌ {name}")

        print(f"\nHealth Score: {score}/{total}")
