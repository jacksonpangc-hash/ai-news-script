"""Build a local Skill-folder ZIP with an explicit clean-file boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
DIRS={'references':{'.md'},'assets':{'.json'},'scripts':{'.py'},'tests':{'.py','.json'}}
ROOT_FILES={'SKILL.md','README.md','INSTALL.md','USAGE.md','CHANGELOG.md','NOTICE.md','LICENSE','agents/openai.yaml'}
PERSONAL_PATH=re.compile(r'(?:/Users/[^/\s]+/|/home/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)')
SECRET=re.compile(r'(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|ghp_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----)')


def check_skill(root):
    root=Path(root)
    text=(root/'SKILL.md').read_text(encoding='utf-8')
    parts=text.split('---',2)
    if len(parts)!=3 or parts[0].strip():raise ValueError('Missing frontmatter')
    # The package deliberately uses a simple frontmatter subset, checked without PyYAML.
    fields={m.group(1):m.group(2).strip() for line in parts[1].splitlines()
            if (m:=re.match(r'^([a-z][a-z_-]*):\s*(.*)$',line))}
    if fields.get('name')!=root.name or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',root.name) or len(root.name)>64:
        raise ValueError('Skill name/folder mismatch')
    if not 0<len(fields.get('description',''))<=1024:raise ValueError('Invalid description')
    if len(text.splitlines())>500:raise ValueError('Entrypoint too long')
    for doc in [*root.glob('*.md'),*(root/'references').glob('*.md')]:
        for target in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):continue
            file=(doc.parent/target.split('#')[0]).resolve()
            if not file.is_relative_to(root.resolve()) or not file.is_file():raise ValueError('Broken or escaping reference: '+target)
    return fields


def vendor_files(root):
    """Only the pinned, hashed upstream subtree crosses the vendor boundary."""
    vendor=root/'vendor/sepia'
    if not vendor.exists():return set()
    data=json.loads((vendor/'UPSTREAM.json').read_text(encoding='utf-8'));allowed={'UPSTREAM.json'}
    if data.get('commit')!='fb06be76abeae7dd606960a32f2b10c1d1798e0d' or data.get('license')!='MIT':
        raise ValueError('Unexpected vendored source')
    for item in data['files']:
        rel=Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe vendor path')
        f=vendor/rel
        if f.is_symlink() or not f.is_file():raise ValueError('Missing vendor file: '+str(rel))
        b=f.read_bytes()
        if hashlib.sha256(b).hexdigest()!=item['sha256']:raise ValueError('Vendor hash mismatch: '+str(rel))
        if hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()!=item['git_blob_sha']:
            raise ValueError('Vendor blob mismatch: '+str(rel))
        allowed.add(rel.as_posix())
    if not {'LICENSE','SKILL.md','references/professional-pass.md','references/languages/zh.md'}.issubset(allowed):
        raise ValueError('Incomplete embedded Sepia')
    return {'vendor/sepia/'+name for name in allowed}


def build(skill,outfile):
    skill=Path(skill);outfile=Path(outfile);check_skill(skill)
    entries=[];vendored=vendor_files(skill)
    for f in sorted(skill.rglob('*'),key=lambda p:p.relative_to(skill).as_posix()):
        if f.is_symlink():raise ValueError('Do not distribute symlinks')
        if not f.is_file():continue
        rel=f.relative_to(skill)
        if '__pycache__' in rel.parts or f.name=='.DS_Store':continue
        allowed=(rel.as_posix() in ROOT_FILES or rel.as_posix() in vendored or
                 (rel.parts[0] in DIRS and f.suffix in DIRS[rel.parts[0]]))
        if not allowed:raise ValueError('Unexpected file in Skill: '+str(rel))
        if f.name in ('preferences.json','event_history.json','config.local.json','run.json','sources.json','script.md'):
            raise ValueError('Runtime file in distributable Skill')
        data=f.read_bytes()
        if SECRET.search(data.decode('utf-8')):raise ValueError('Possible credential in '+str(rel))
        if PERSONAL_PATH.search(data.decode('utf-8')):raise ValueError('Possible personal machine path in '+str(rel))
        entries.append(((Path(skill.name)/rel).as_posix(),data))
    outfile.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(outfile,'w',compression=ZIP_DEFLATED) as z:
        for name,data in entries:
            info=ZipInfo(name,date_time=(2026,10,25,0,0,0));info.create_system=3;info.compress_type=ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,data)
    return outfile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    version=re.search(r'^  version: "([0-9]+\.[0-9]+\.[0-9]+)"$',(ROOT/'ai-news-script/SKILL.md').read_text(encoding='utf-8'),re.M)
    if not version:raise ValueError('Missing package version')
    p.add_argument('--output',type=Path,default=ROOT/('dist/ai-news-script-v'+version.group(1)+'.zip'))
    args=p.parse_args();archive=build(ROOT/'ai-news-script',args.output)
    with ZipFile(archive) as z:files=z.namelist()
    result=dict(archive=archive.name,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                file_count=len(files),files=files,checks=['frontmatter_subset','local_links_including_install_docs','allowlisted_files','credential_pattern_scan','personal_path_scan'],
                limits=['Pattern scan cannot prove absence of every possible secret','No automatic host-discovery claim'])
    archive.with_suffix('.manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
