import os
import sys

# Configure stdout to use utf-8
sys.stdout.reconfigure(encoding='utf-8')

def search_text(directory, term):
    results = []
    ignore_dirs = {"venv", "node_modules", ".git", "__pycache__", ".svelte-kit", "build", "dist"}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if file.endswith((".py", ".js", ".jsx", ".html", ".json", ".ts", ".tsx")):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if term in line:
                                results.append((path, line_num, line.strip()))
                except Exception as e:
                    pass
    return results

if __name__ == "__main__":
    found = search_text(".", "BusDetailPanel")
    print(f"Found {len(found)} matches for 'BusDetailPanel':")
    for path, line_num, line in found[:100]:
        print(f"{path}:{line_num}: {line}")

