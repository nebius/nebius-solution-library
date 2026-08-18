# OpenFold2 new-node benchmark result

Run `of2-newnode-r4-0418` completed with both the frozen canary receipt and the
lifecycle receipt at `PASS`. The true demand edge was the exact node-group
`0 -> 1` request at `2026-08-18T04:21:09.698504003Z`.

| Phase from demand | Seconds |
| --- | ---: |
| Strict new-node admission | 119.055 |
| CRIU agent Ready | 119.765 |
| Target created/scheduled | 125.301 |
| Placeholder process start | 586.301 |
| Native restore receipt | 605.152 |
| HTTP Ready | 605.301 |
| Two strict semantic responses | 607.247 |
| Benchmark PASS recorded | 621.948 |
| Full cleanup and holder restoration | 810.310 |

The exact 10,698,531,042-byte OpenFold2 image took 251.094 seconds to cold-pull
from the original NGC registry. That registry transfer is the dominant
avoidable portion of the current result. A byte-identical regional mirror is
now qualified in [`REGIONAL_MIRROR_RESULT.md`](REGIONAL_MIRROR_RESULT.md), but
has not yet been timed in a second true new-node lifecycle.
The native restore itself took 4.083 seconds; the two semantic requests took
1.917 seconds and 1.055 seconds.

The fresh node initially lacked `profiles/block-iouring.json`. A run-owned
installer copied the exact existing ConfigMap payload (SHA-256
`ebbe5e221b6b331bb84efbdfea7adb88e9dddab62a2ea901598bad09fe7f76a0`), and
the target recovered on the same demand clock. The settled runner now performs
that preparation automatically with a digest-pinned BusyBox image and deletes
the installer by its server-returned UID after target start.

Cleanup restored node-group counts to `1/1/1/1`, removed all run-labelled
resources, recreated the holder Ready on its fixed node, and confirmed both RWO
volumes attached there.
