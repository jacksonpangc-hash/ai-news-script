"""Read the actual entry; no network or writes. A version label is not host-discovery proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def read_identity(root=None, expected_version=None):
    root=Path(root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    entry=root/'SKILL.md';data=entry.read_bytes();text=data.decode('utf-8')
    match=re.search(r'^  version: "([0-9]+\.[0-9]+\.[0-9]+)"$',text,re.M)
    if not match:raise ValueError('entry_version_missing')
    version=match.group(1)
    if expected_version is not None and expected_version!=version:
        raise ValueError('version_mismatch: requested '+str(expected_version)+', loaded '+version)
    package=json.loads((root/'assets/package-identity.json').read_text(encoding='utf-8'))
    if package.get('version')!=version:raise ValueError('package_entry_version_mismatch')
    return dict(name='ai-news-script',version=version,entry_path=str(entry),
                entry_sha256=hashlib.sha256(data).hexdigest(),package_id=package['package_id'],
                expected_version=expected_version,verification='actual_entry_bytes')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--expected-version');p.add_argument('--root')
    args=p.parse_args()
    try:print(json.dumps(read_identity(args.root,args.expected_version),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as exc:p.exit(2,str(exc)+'\n')
