import os
import json
import pathlib
from openai import OpenAI
import subprocess

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ALLOWED_EXTENSIONS = {".py", ".js", ".ts", ".go", ".java", ".rb", ".php"}


def load_changed_files():
    """
    Reads the GitHub event payload to extract changed files in the PR.
    Works for pull_request and pull_request_target events.
    """
    event_path = os.getenv("GITHUB_EVENT_PATH")
    print("GITHUB_EVENT_PATH:", event_path)
    if not event_path or not pathlib.Path(event_path).exists():
        raise RuntimeError(
            "GITHUB_EVENT_PATH not found. "
            "Are you running inside GitHub Actions?"
        )

    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)

    # GitHub provides changed files under the "pull_request" → "files" API,
    # but the event payload does NOT include them directly.
    # So we rely on the GitHub CLI (gh) or fallback to reviewing all files.
    pr_number = event.get("number")
    print("PR Number:", pr_number)
    repo = os.getenv("GITHUB_REPOSITORY")
    print("Repository:", repo)

    if not pr_number or not repo:
        raise RuntimeError("Missing PR number or repository info.")

    # Use GitHub CLI to fetch changed files
    import subprocess
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo,
            "--json",
            "files"
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch PR files: {result.stderr}")

    data = json.loads(result.stdout)
    files = [f["path"] for f in data.get("files", [])]

    print("Changed files:", files)
    return files


def filter_source_files(files):
    """Return only files with allowed extensions."""
    filtered = []
    for f in files:
        ext = pathlib.Path(f).suffix
        if ext in ALLOWED_EXTENSIONS:
            filtered.append(f)
    return filtered


def get_diff_positions(file_path):
    """
    Returns a mapping: { line_number_in_file: diff_position }
    """
    cmd = ["gh", "pr", "diff", "--patch", file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return {}

    print(f"Diff for {file_path}:\n", result.stdout)
    diff = result.stdout.splitlines()

    positions = {}
    file_line = 0
    diff_pos = 0

    for line in diff:
        diff_pos += 1

        if line.startswith("@@"):
            # Example: @@ -1,5 +1,7 @@
            hunk = line.split(" ")[2]  # "+1,7"
            start = int(hunk.split(",")[0].replace("+", ""))
            file_line = start - 1
            continue

        if line.startswith("+") and not line.startswith("+++"):
            file_line += 1
            positions[file_line] = diff_pos
        elif not line.startswith("-"):
            file_line += 1

    print(f"Diff positions for {file_path}:", positions)
    return positions


def review_file(path):
    """Send a single file to the LLM for review."""
    try:
        content = pathlib.Path(path).read_text(encoding="utf-8")
    except Exception as e:
        return f"Could not read {path}: {e}"

    prompt = f"""
    You are an expert software engineer. Review the following file.

    Return ONLY valid JSON in this exact format:

    [
    {{"line": <line_number>, "comment": "<text>"}},
    ...
    ]

    Rules:
    - Only include lines that have issues.
    - Use absolute line numbers from the file.
    - Do not include explanations outside the JSON.
    - Do not include markdown.
    - Do not include headings.
    - Do not include prose.
    - Do not wrap the JSON in code fences.

    FILE PATH: {path}
    FILE CONTENT:
    {content}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800
    )

    ai_text = response.choices[0].message.content
    print(f"AI Review for {path}:\n{ai_text}\n")

    try:
        data = json.loads(ai_text)
        comments = [(item["line"], item["comment"]) for item in data]
        print("Extracted comments:", comments)
        return comments
    except Exception:
        print("Failed to parse JSON:", ai_text)
        return []


def run_review():
    changed_files = load_changed_files()
    source_files = filter_source_files(changed_files)
    all_comments = []

    for f in source_files:
        print(f"--- Reviewing {f} ---")
        file_comments = review_file(f)

        if not file_comments:
            continue

        diff_map = get_diff_positions(f)

        for (line_num, body) in file_comments:
            if line_num in diff_map:
                all_comments.append({
                    "path": f,
                    "position": diff_map[line_num],
                    "body": body
                })

    # Write GitHub review JSON
    review_json = {
        "body": "AI Code Review",
        "event": "COMMENT",
        "comments": all_comments
    }

    print("=== REVIEW JSON ===")
    print(json.dumps(review_json, indent=2))
    print("====================")

    with open("review_output.json", "w") as out:
        json.dump(review_json, out, indent=2)

    print("Generated review_output.json with inline comments.")


if __name__ == "__main__":
    run_review()
