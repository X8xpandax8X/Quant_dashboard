#!/usr/bin/env python3
"""Verify the project's normative DESIGN.md values against the runtime CSS."""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
design = (root / "DESIGN.md").read_text()
css = (root / "frontend/src/styles/tokens.css").read_text()
frontmatter = design.split("---", 2)[1]
variables = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", css))
aliases = {"background": "--bg", "foreground": "--fg"}
color_section = frontmatter.split("colors:\n", 1)[1].split("\ntypography:", 1)[0]
expected = {
    aliases.get(name, f"--{name}"): value
    for name, value in re.findall(r"^  (\w+): ['\"]?(#[\da-fA-F]{6})", color_section, re.M)
}
for section, name, variable in [
    ("rounded", "DEFAULT", "--radius"),
    ("rounded", "control", "--control-radius"),
    ("spacing", "unit", "--space"),
]:
    block = re.search(rf"^{section}:\n((?: +.*\n)+)", frontmatter, re.M).group(1)
    expected[variable] = re.search(rf"^  {name}: ['\"]?([^'\"\n]+)", block, re.M).group(1)
errors = [f"{key}: expected {value}, found {variables.get(key, 'missing')}"
          for key, value in expected.items()
          if variables.get(key, "").strip().lower() != value.lower()]
for family in re.findall(r"fontFamily: ['\"]([^,'\"]+)", frontmatter):
    if family not in css:
        errors.append(f"Missing declared font family: {family}")
if errors:
    raise SystemExit("Design token mismatch:\n" + "\n".join(errors))
print(f"Design tokens match: {len(expected)} values and both font families.")
