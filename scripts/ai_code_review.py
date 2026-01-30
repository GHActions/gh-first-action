import os
import json
import pathlib
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ALLOWED_EXTENSIONS = {".py", ".js", ".ts", ".go", ".java", ".rb", ".php"}

def load_changed_files():
    """
    Reads the GitHub event payload to extract changed files in the PR.
    Works for pull_request and pull_request_target events.
    """
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path or not pathlib.Path(event_path).exists():
        raise RuntimeError("GITHUB_EVENT_PATH not found. Are you running inside GitHub Actions?")

    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)

    # GitHub provides changed files under the "pull_request" → "files" API,
    # but the event payload does NOT include them directly.
    # So we rely on the GitHub CLI (gh) or fallback to reviewing all files.
    pr_number = event.get("number")
    repo = os.getenv("GITHUB_REPOSITORY")

    if not pr_number or not repo:
        raise RuntimeError("Missing PR number or repository info.")

    # Use GitHub CLI to fetch changed files
    import subprocess
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "files"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch PR files: {result.stderr}")

    data = json.loads(result.stdout)
    files = [f["path"] for f in data.get("files", [])]

    return files


def filter_source_files(files):
    """Return only files with allowed extensions."""
    filtered = []
    for f in files:
        ext = pathlib.Path(f).suffix
        if ext in ALLOWED_EXTENSIONS:
            filtered.append(f)
    return filtered


def review_file(path):
    """Send a single file to the LLM for review."""
    try:
        content = pathlib.Path(path).read_text(encoding="utf-8")
    except Exception as e:
        return f"Could not read {path}: {e}"

    prompt = f"""
You are an expert software engineer. Review the following file for:
- bugs
- security issues
- code smells
- missing edge cases
- readability problems
- opportunities for simplification

Respond with a structured list of findings.

FILE PATH: {path}
FILE CONTENT:
{content}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800
    )

    return response.choices[0].message["content"]


def run_review():
    print("### AI Code Review Report ###\n")

    changed_files = load_changed_files()
    source_files = filter_source_files(changed_files)

    if not source_files:
        print("No source files changed in this PR.")
        return

    for f in source_files:
        print(f"\n--- Reviewing {f} ---\n")
        result = review_file(f)
        print(result)


if __name__ == "__main__":
    run_review()