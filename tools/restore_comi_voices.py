#!/usr/bin/env python3
"""Restore damaged disc-1 entries from matching disc-2 entries, with native decode checks."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

from audit_comi_audio import audit
from comi_audio import atomic_json, digest, ensure_stopped


def build_decoder(target, work):
    source = target / '.playtest/engine/source'
    adpcm = (source / 'audio/decoders/adpcm.cpp').read_text()
    table = re.search(r'const int16 Ima_ADPCMStream::_imaTable\[89\] = \{.*?\};', adpcm, re.S).group()
    harness = r'''
#define FORBIDDEN_SYMBOL_ALLOW_ALL
#include <cstdio>
#include <cstdlib>
#include <cstdarg>
#include <vector>
#include "common/scummsys.h"
#include "audio/decoders/adpcm_intern.h"
#include "scumm/imuse_digi/dimuse_codecs.h"
void error(const char *format, ...) { va_list args; va_start(args,format); vfprintf(stderr,format,args); va_end(args); exit(2); }
namespace Audio { TABLE }
unsigned be(const unsigned char *p) { return (unsigned(p[0])<<24)|(unsigned(p[1])<<16)|(unsigned(p[2])<<8)|p[3]; }
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    FILE *in=fopen(argv[1],"rb"); if(!in) return 2;
    fseek(in,0,SEEK_END); long size=ftell(in); rewind(in);
    std::vector<unsigned char> data(size); if(fread(data.data(),1,size,in)!=(size_t)size) return 2; fclose(in);
    if(size<16 || memcmp(data.data(),"COMP",4)) return 2;
    unsigned count=be(data.data()+4), last=be(data.data()+12);
    if(!count || count>(size-16)/16 || last>0x2000) return 2;
    Scumm::BundleCodecs::initializeImcTables();
    FILE *out=fopen(argv[2],"wb"); if(!out) return 2;
    for(unsigned i=0;i<count;i++) {
        const unsigned char *row=data.data()+16+i*16;
        unsigned offset=be(row), length=be(row+4), codec=be(row+8);
        if(offset<16+count*16 || (uint64)offset+length>(uint64)size || !length) return 2;
        std::vector<unsigned char> input(length+1,0), output(0x2000);
        memcpy(input.data(),data.data()+offset,length);
        int n=Scumm::BundleCodecs::decompressCodec(codec,input.data(),output.data(),length);
        if(n<=0 || n>0x2000 || (i+1==count && last>(unsigned)n)) return 2;
        if(i+1==count && last) n=last;
        fwrite(output.data(),1,n,out);
    }
    fclose(out); Scumm::BundleCodecs::releaseImcTables(); return 0;
}
'''.replace('TABLE', table)
    cpp, binary = work / 'decode.cpp', work / 'decode'
    cpp.write_text(harness)
    subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-g', '-DHAVE_CONFIG_H',
        '-I'+str(target / '.playtest/engine/build'), '-I'+str(source), '-I'+str(source / 'engines'),
        str(cpp), str(source / 'engines/scumm/imuse_digi/dimuse_codecs.cpp'), '-o', str(binary)], check=True)
    return binary


def prepare(target, work):
    work.mkdir(parents=True, exist_ok=True)
    resource = target / '.playtest/game/RESOURCE'
    source, donor = resource / 'VOXDISK1.BUN', resource / 'VOXDISK2.BUN'
    first, second = audit(source), audit(donor)
    if first['errors'] or second['errors']:
        raise ValueError('Cannot repair an invalid bundle directory')
    lookup = {e['name']: e for e in second['entries']}
    shared = [e for e in first['entries'] if e['status'] == 'valid_structure' and e['name'] in lookup]
    if not shared or any(e['sha256'] != lookup[e['name']].get('sha256') for e in shared):
        raise ValueError('Shared healthy entries disagree: donor edition is not verified')
    repairs = [e for e in first['entries'] if e['status'] == 'invalid' and
               lookup.get(e['name'], {}).get('status') == 'valid_structure']
    if not repairs:
        raise ValueError('No damaged entries with intact disc-2 counterparts')
    decoder = build_decoder(target, work)
    repaired = work / 'VOXDISK1.BUN'
    shutil.copyfile(source, repaired)
    records = []
    with repaired.open('r+b') as output, donor.open('rb') as donor_file:
        output.seek(4)
        directory = struct.unpack('>I', output.read(4))[0]
        for broken in repairs:
            replacement = lookup[broken['name']]
            donor_file.seek(replacement['offset'])
            payload = donor_file.read(replacement['size'])
            compressed, decoded = work / 'entry.comp', work / 'entry.imus'
            compressed.write_bytes(payload)
            subprocess.run([str(decoder), str(compressed), str(decoded)], check=True, capture_output=True)
            data = decoded.read_bytes()
            if data[:4] != b'iMUS' or data[8:12] != b'MAP ' or b'FRMT' not in data[:256] or b'DATA' not in data:
                raise ValueError('Decoded replacement has no valid iMUS structure: ' + broken['name'])
            output.seek(0, 2)
            offset = output.tell()
            output.write(payload)
            output.seek(directory + broken['index']*20 + 12)
            output.write(struct.pack('>II', offset, len(payload)))
            records.append(dict(name=broken['name'], index=broken['index'], donor_index=replacement['index'],
                                payload_sha256=replacement['sha256'], decoded_sha256=digest(decoded)))
    checked = audit(repaired)
    fixed = {e['name']:e for e in checked['entries']}
    repaired_names = {e['name'] for e in repairs}
    for entry in first['entries']:
        expected = lookup[entry['name']]['sha256'] if entry['name'] in repaired_names else entry.get('sha256')
        if fixed[entry['name']].get('sha256') != expected:
            raise ValueError('Repaired bundle changed an unrelated payload')
    manifest = dict(status='prepared', original_sha256=first['sha256'], donor_sha256=second['sha256'],
        prepared_sha256=digest(repaired), shared_healthy_identical=len(shared), repairs=records,
        remaining_invalid=checked['counts'].get('invalid',0), target_workspace=str(target))
    atomic_json(work / 'repair.json', manifest)
    print(f"Prepared {len(records)} repairs; {manifest['remaining_invalid']} entries still damaged")


def apply(target, work, undo=False):
    ensure_stopped(target)
    manifest_path = work / 'repair.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest['target_workspace'] != str(target):
        raise ValueError('Repair was prepared for another workspace')
    bundle = target / '.playtest/game/RESOURCE/VOXDISK1.BUN'
    backup = work / 'VOXDISK1.original.BUN'
    if undo:
        expected, replacement = manifest['prepared_sha256'], backup
        replacement_hash = manifest['original_sha256']
    else:
        expected, replacement = manifest['original_sha256'], work / 'VOXDISK1.BUN'
        replacement_hash = manifest['prepared_sha256']
        if digest(bundle) == replacement_hash:
            print('Voice repair already installed')
            return
        if digest(bundle.with_name('VOXDISK2.BUN')) != manifest['donor_sha256']:
            raise ValueError('Donor bundle changed since validation')
    if digest(bundle) != expected or digest(replacement) != replacement_hash:
        raise ValueError('Bundle changed since validation; refusing replacement')
    if not undo:
        if backup.exists() and digest(backup) != expected:
            raise ValueError('Existing voice backup differs')
        if not backup.exists():
            shutil.copy2(bundle, backup)
    staging = bundle.with_suffix('.repair.tmp')
    shutil.copy2(replacement, staging)
    if digest(staging) != replacement_hash:
        raise ValueError('Voice staging checksum mismatch')
    ensure_stopped(target)
    staging.replace(bundle)
    manifest['status'] = 'rolled_back' if undo else 'installed'
    atomic_json(manifest_path, manifest)
    print('Voice repair ' + manifest['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install', 'rollback'])
    parser.add_argument('--target-workspace', required=True, type=Path)
    parser.add_argument('--work-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'downloads/voice-repair')
    args = parser.parse_args()
    target, work = args.target_workspace.resolve(), args.work_dir.resolve()
    lock_path = work / '.prepare.lock' if args.action == 'prepare' else target / '.playtest/audio-tool.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'prepare':
            prepare(target, work)
        else:
            apply(target, work, args.action == 'rollback')
