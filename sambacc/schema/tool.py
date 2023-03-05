#!/usr/bin/python3
"""Convert or compare schema files written in YAML to the corresponding
files stored in JSON.
"""

import argparse
import collections
import json
import os
import pprint
import subprocess
import sys

import yaml


nameparts = collections.namedtuple("nameparts", "full head ext")
filepair = collections.namedtuple("filepair", "origin dest format")


def _namesplit(name):
    head, ext = name.split(".", 1)
    return nameparts(name, head, ext)


def _pyname(np):
    head = np.head.replace("-", "_")
    if np.ext.startswith("schema."):
        head += "_schema"
    ext = "py"
    return nameparts(f"{head}.{ext}", head, ext)


def _format_black(path):
    # black does not formally have an api. Safeset way to use it is via
    # the cli
    path = os.path.abspath(path)
    # the --preview arg allows black to break up long strings that
    # the general check would discover and complain about. Otherwise
    # we'd be forced to ignore the formatting on these .py files.
    subprocess.run(["black", "-l78", "--preview", path], check=True)


def match(files):
    yamls = []
    jsons = []
    pys = []
    for fname in files:
        try:
            np = _namesplit(fname)
        except ValueError:
            continue
        if np.ext == "schema.yaml":
            yamls.append(np)
        if np.ext == "schema.json":
            jsons.append(np)
        if np.ext == "py":
            pys.append(np)
    pairs = []
    for yname in yamls:
        for jname in jsons:
            if jname.head == yname.head:
                pairs.append(filepair(yname, jname, "JSON"))
                break
        else:
            pairs.append(filepair(yname, None, "JSON"))
        for pyname in pys:
            if _pyname(yname).head == pyname.head:
                pairs.append(filepair(yname, pyname, "PYTHON"))
                break
        else:
            pairs.append(filepair(yname, None, "PYTHON"))
    return pairs


def report(func, path, yaml_file, json_file, fmt):
    needs_update = func(path, yaml_file, json_file, fmt)
    json_name = "---" if not json_file else json_file.full
    if not needs_update:
        print(f"{yaml_file.full} -> {fmt.lower()}:{json_name}   OK")
        return None
    print(f"{yaml_file.full} -> {fmt.lower()}:{json_name}   MISMATCH")
    return True


def update_json(path, yaml_file, json_file):
    yaml_path = os.path.join(path, yaml_file.full)
    json_path = os.path.join(path, f"{yaml_file.head}.schema.json")
    with open(yaml_path) as fh:
        yaml_data = yaml.safe_load(fh)
    with open(json_path, "w") as fh:
        json.dump(yaml_data, fh, indent=2)


def compare_json(path, yaml_file, json_file):
    if json_file is None:
        return True
    yaml_path = os.path.join(path, yaml_file.full)
    json_path = os.path.join(path, json_file.full)
    with open(yaml_path) as fh:
        yaml_data = yaml.safe_load(fh)
    with open(json_path) as fh:
        json_data = json.load(fh)
    return yaml_data != json_data


def update_py(path, yaml_file, py_file):
    yaml_path = os.path.join(path, yaml_file.full)
    py_path = os.path.join(path, _pyname(yaml_file).full)
    with open(yaml_path) as fh:
        yaml_data = yaml.safe_load(fh)
    out = []
    out.append("#!/usr/bin/python3")
    out.append("# --- GENERATED FILE --- DO NOT EDIT --- #")
    out.append(f"# --- generated from: {yaml_file.full}")
    out.append("")
    out.append(
        "SCHEMA = " + pprint.pformat(yaml_data, width=800, sort_dicts=False)
    )
    content = "\n".join(out)
    with open(py_path, "w") as fh:
        fh.write(content)
    _format_black(py_path)


def compare_py(path, yaml_file, py_file):
    if py_file is None:
        return True
    yaml_path = os.path.join(path, yaml_file.full)
    py_path = os.path.join(path, py_file.full)
    with open(yaml_path) as fh:
        yaml_data = yaml.safe_load(fh)
    with open(py_path) as fh:
        py_locals = {}
        exec(fh.read(), None, py_locals)
    py_data = py_locals.get("SCHEMA") or {}
    return yaml_data != py_data


def update(path, yaml_data, other_file, fmt):
    if fmt == "PYTHON":
        return update_py(path, yaml_data, other_file)
    return update_json(path, yaml_data, other_file)


def compare(path, yaml_data, other_file, fmt):
    if fmt == "PYTHON":
        return compare_py(path, yaml_data, other_file)
    return compare_json(path, yaml_data, other_file)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("DIR", default=os.path.dirname(__file__), nargs="?")
    parser.add_argument("--update", action="store_true")
    cli = parser.parse_args()

    mismatches = []
    os.chdir(cli.DIR)
    fn = update if cli.update else compare
    pairs = match(os.listdir("."))
    for pair in pairs:
        mismatches.append(report(fn, ".", *pair))
    if any(mismatches):
        sys.exit(1)


if __name__ == "__main__":
    main()
