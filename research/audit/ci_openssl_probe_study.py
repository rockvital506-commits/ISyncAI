#!/usr/bin/env python3
"""CI-диагностика только публичного RFC 8032 TEST 2, не проверка релизных ключей."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

KEY=bytes.fromhex('302a300506032b65700321003d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c')
SIG=bytes.fromhex('92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da08'
                  '5ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00')


def main():
    with tempfile.TemporaryDirectory(prefix='public-rfc-vector-') as d:
        root=Path(d);(root/'pub').write_bytes(KEY);(root/'sig').write_bytes(SIG)
        env={'PATH':'/usr/bin:/bin','LC_ALL':'C','HOME':d,'OPENSSL_CONF':'/dev/null'}
        version=subprocess.run(['/usr/bin/openssl','version'],cwd=root,env=env,capture_output=True,text=True,timeout=10)
        rows=[]
        for message in (b'\x72',b'\x73'):
            (root/'message').write_bytes(message)
            p=subprocess.run(['/usr/bin/openssl','pkeyutl','-verify','-pubin','-keyform','DER','-inkey','pub',
                              '-rawin','-in','message','-sigfile','sig'],cwd=root,env=env,capture_output=True,text=True,timeout=10)
            rows.append({'message':message.hex(),'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        result={'openssl_version':version.stdout.strip(),'version_exit':version.returncode,'public_vectors':rows}
        text=json.dumps(result,ensure_ascii=True,sort_keys=True)
        if os.environ.get('GITHUB_ACTIONS')=='true':
            print('::notice::'+text.replace('%','%25').replace('\r','%0D').replace('\n','%0A'),flush=True)
        else:print(text)
        return 0


if __name__=='__main__':raise SystemExit(main())
